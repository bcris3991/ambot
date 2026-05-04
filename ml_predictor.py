"""
ml_predictor.py
---------------
Demand Prediction for WMSU Book Inventory System
Gamit: Linear Regression (scikit-learn)

Gi-predict niini ang expected borrow count sa matag book
base sa historical borrow data (per month).
"""

import sqlite3
import os
from datetime import datetime, timedelta

import numpy as np

# Graceful import — mag-warn lang kung wala pa gi-install ang scikit-learn
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import LabelEncoder
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ─── MAIN PREDICTION FUNCTION ─────────────────────────────────────────────────

def predict_demand(db_path: str) -> list[dict]:
    """
    Basaha ang borrow_requests table ug i-predict ang demand sa sunod na bulan
    para sa matag book/item.

    Returns:
        list of dicts:
        [
            {
                'item_id': int,
                'item_name': str,
                'category': str,
                'avg_monthly_borrows': float,
                'predicted_next_month': int,
                'trend': str,          # 'Rising', 'Stable', 'Declining'
                'confidence': str,     # 'High', 'Medium', 'Low'
                'total_borrows': int,
                'months_of_data': int,
            },
            ...
        ]
    """
    if not SKLEARN_AVAILABLE:
        return _fallback_simple_average(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Kuhaon ang tanan borrow records (Approved + Returned lang — confirmed borrows)
    rows = cur.execute("""
        SELECT
            br.item_id,
            i.item_name,
            i.category,
            strftime('%Y-%m', br.created_at) AS borrow_month,
            COUNT(*) AS borrow_count
        FROM borrow_requests br
        JOIN items i ON br.item_id = i.item_id
        WHERE br.status IN ('Approved', 'Returned')
        GROUP BY br.item_id, borrow_month
        ORDER BY br.item_id, borrow_month
    """).fetchall()

    conn.close()

    if not rows:
        return _fallback_with_pending(db_path)

    # Organize data per item
    items_data: dict[int, dict] = {}
    for row in rows:
        iid = row['item_id']
        if iid not in items_data:
            items_data[iid] = {
                'item_name': row['item_name'],
                'category': row['category'],
                'monthly': {}
            }
        items_data[iid]['monthly'][row['borrow_month']] = row['borrow_count']

    results = []
    for item_id, data in items_data.items():
        monthly = data['monthly']
        months_sorted = sorted(monthly.keys())
        counts = [monthly[m] for m in months_sorted]
        n = len(counts)

        avg = sum(counts) / n
        total = sum(counts)

        if n >= 2:
            # Linear regression: X = month index, y = borrow count
            X = np.array(range(n)).reshape(-1, 1)
            y = np.array(counts, dtype=float)
            model = LinearRegression()
            model.fit(X, y)
            predicted = max(0, round(model.predict([[n]])[0]))
            slope = model.coef_[0]

            if slope > 0.5:
                trend = 'Rising'
            elif slope < -0.5:
                trend = 'Declining'
            else:
                trend = 'Stable'

            confidence = 'High' if n >= 4 else 'Medium'
        else:
            # Only 1 month of data — use average as prediction
            predicted = round(avg)
            trend = 'Stable'
            confidence = 'Low'

        results.append({
            'item_id': item_id,
            'item_name': data['item_name'],
            'category': data['category'],
            'avg_monthly_borrows': round(avg, 1),
            'predicted_next_month': predicted,
            'trend': trend,
            'confidence': confidence,
            'total_borrows': total,
            'months_of_data': n,
        })

    # Sort by predicted demand (highest first)
    results.sort(key=lambda x: x['predicted_next_month'], reverse=True)
    return results


def _fallback_with_pending(db_path: str) -> list[dict]:
    """
    Fallback: kung wala pay Approved/Returned records,
    gamiton ang Pending requests para makakuha ug datos.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT
            br.item_id,
            i.item_name,
            i.category,
            COUNT(*) as total_requests
        FROM borrow_requests br
        JOIN items i ON br.item_id = i.item_id
        GROUP BY br.item_id
        ORDER BY total_requests DESC
    """).fetchall()

    conn.close()

    results = []
    for row in rows:
        results.append({
            'item_id': row['item_id'],
            'item_name': row['item_name'],
            'category': row['category'],
            'avg_monthly_borrows': float(row['total_requests']),
            'predicted_next_month': row['total_requests'],
            'trend': 'Stable',
            'confidence': 'Low',
            'total_borrows': row['total_requests'],
            'months_of_data': 1,
        })
    return results


def _fallback_simple_average(db_path: str) -> list[dict]:
    """
    Fallback kung wala gi-install si scikit-learn.
    Gamiton ang simple average ra.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT
            br.item_id,
            i.item_name,
            i.category,
            COUNT(*) as total,
            COUNT(DISTINCT strftime('%Y-%m', br.created_at)) as months
        FROM borrow_requests br
        JOIN items i ON br.item_id = i.item_id
        WHERE br.status IN ('Approved','Returned','Pending')
        GROUP BY br.item_id
        ORDER BY total DESC
    """).fetchall()

    conn.close()

    results = []
    for row in rows:
        months = max(row['months'], 1)
        avg = row['total'] / months
        results.append({
            'item_id': row['item_id'],
            'item_name': row['item_name'],
            'category': row['category'],
            'avg_monthly_borrows': round(avg, 1),
            'predicted_next_month': round(avg),
            'trend': 'Stable',
            'confidence': 'Low (install scikit-learn for ML)',
            'total_borrows': row['total'],
            'months_of_data': months,
        })
    return results


def get_category_summary(predictions: list[dict]) -> list[dict]:
    """
    I-group ang predictions by category para sa chart.
    """
    summary: dict[str, int] = {}
    for p in predictions:
        cat = p['category']
        summary[cat] = summary.get(cat, 0) + p['predicted_next_month']

    return [
        {'category': cat, 'predicted_demand': total}
        for cat, total in sorted(summary.items(), key=lambda x: x[1], reverse=True)
    ]
