# WMSU Inventory & Borrowing Management System

A full-stack web application built with Python Flask, SQLite, HTML, CSS, and JavaScript.

## Default Credentials

| Role    | Email                   | Password  |
|---------|-------------------------|-----------|
| Admin   | admin@wmsu.edu.ph       | admin123  |
| Staff   | staff@wmsu.edu.ph       | staff123  |
| Student | Register via /register  | (yours)   |

## Quick Start

### 1. Prerequisites
- Python 3.8 or higher
- pip

### 2. Setup

```bash
# Clone / extract the project
cd wmsu_inventory

# Create a virtual environment (recommended)
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

### 3. Open in browser
Navigate to: **http://127.0.0.1:5000**

The database (SQLite) is created automatically on first run at `instance/wmsu_inventory.db`

---

## Features

### Student
- Browse & search available inventory items
- Submit borrow requests with due date
- Return borrowed items
- View request history with status tracking
- Receive notifications on approval/rejection

### Staff
- Full inventory management (add/edit/delete items)
- Approve or reject borrow requests
- Manage item quantities and status
- View all borrow requests

### Admin
- Everything Staff can do
- User management (add/edit/delete users)
- Assign roles (Student/Staff/Admin)
- Reports & analytics dashboard
- View overdue items and most borrowed items

## Project Structure

```
wmsu_inventory/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── README.md
├── instance/
│   └── wmsu_inventory.db   # SQLite database (auto-created)
└── templates/
    ├── base.html           # Shared layout with sidebar
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── items.html
    ├── requests.html
    ├── users.html
    ├── reports.html
    ├── notifications.html
    └── profile.html
```

## Database Schema

```sql
users (id, name, email, password, role, created_at)
items (item_id, item_name, description, category, quantity, status, created_at)
borrow_requests (request_id, user_id, item_id, quantity_requested,
                 date_borrowed, due_date, date_returned, status, notes, created_at)
notifications (id, user_id, message, is_read, created_at)
```

## Tech Stack
- **Backend**: Python Flask
- **Database**: SQLite (via Python's built-in sqlite3)
- **Frontend**: HTML5, CSS3, JavaScript (vanilla)
- **Icons**: Font Awesome 6
- **Fonts**: DM Sans + DM Serif Display (Google Fonts)
- **Auth**: Flask sessions + Werkzeug password hashing
