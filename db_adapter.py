import os
import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import pymysql

SAMPLE_EMPLOYEES = [
    (1, "Suresh", "Engineering Manager", "Available", "Engineering", None, 15),
    (2, "Rahul", "Senior Developer", "Available", "Engineering", 1, 8),
    (3, "Priya", "HR Director", "In Meeting", "HR", None, 12),
    (4, "Arjun", "DevOps Lead", "Available", "IT", 1, 10),
    (5, "Ayush", "Product Intern", "On Leave", "Engineering", 1, 4),
    (6, "Neha", "Marketing Lead", "Available", "Marketing", None, 18),
    (7, "Rohan", "Financial Analyst", "Available", "Finance", None, 14),
    (8, "Ananya", "UI/UX Designer", "Working Remotely", "Design", 1, 9),
    (9, "Vikram", "Senior Sales Executive", "Traveling", "Sales", None, 11),
    (10, "Tanya", "HR Generalist", "In Meeting", "HR", 3, 16),
    (11, "Rohit", "Cloud Security Engineer", "Available", "IT", 4, 7),
    (12, "Sneha", "Lead Product Manager", "Available", "Product", 1, 13),
]

SAMPLE_POLICIES = [
    ("Leave Policy", "Employees are entitled to 20 paid vacation days, 10 sick leaves, and 3 personal floating holidays per year."),
    ("WFH Policy", "Employees can work remotely up to 3 days per week with manager coordination and Core Hours availability (10 AM - 4 PM)."),
    ("Medical Policy", "Comprehensive health, dental, and vision insurance covered 100% by the company, with a $1,000 annual wellness stipend."),
    ("Travel Policy", "Company reimburses airfare, 4-star lodging, local transit, and provides a $75 daily meal per diem for business travel."),
    ("Parental Leave Policy", "Offers 26 weeks of fully paid maternity leave and 12 weeks of fully paid paternity/adoption leave."),
    ("Learning & Development Policy", "Provides $1,500 annual budget per employee for tech certifications, books, and professional conferences."),
    ("Equipment Policy", "All employees receive an Apple MacBook Pro M3 or Dell XPS, dual 4K monitors, and a $500 home ergonomics setup allowance."),
]

SAMPLE_DEPARTMENTS = [
    ("Engineering", "Suresh", "eng@company.com"),
    ("HR", "Priya", "hr@company.com"),
    ("IT", "Arjun", "it@company.com"),
    ("Marketing", "Neha", "marketing@company.com"),
    ("Finance", "Rohan", "finance@company.com"),
    ("Design", "Ananya", "design@company.com"),
    ("Sales", "Vikram", "sales@company.com"),
    ("Product", "Sneha", "product@company.com"),
]


class BaseDatabase(ABC):
    """Abstract interface for IntraBot data access layer."""

    @abstractmethod
    def init_db(self) -> None:
        """Initialize database schema."""
        pass

    @abstractmethod
    def seed_data(self) -> None:
        """Seed sample data."""
        pass

    @abstractmethod
    def get_employee_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Return availability status for an employee."""
        pass

    @abstractmethod
    def get_leave_balance(self, name: str) -> Optional[Dict[str, Any]]:
        """Return leave balance for an employee."""
        pass

    @abstractmethod
    def get_employee_leave_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Return detailed leave status, role, dept, and manager approver."""
        pass

    @abstractmethod
    def get_approver(self, name: str) -> Optional[Dict[str, Any]]:
        """Return reporting manager for an employee."""
        pass

    @abstractmethod
    def list_employees(self) -> List[Dict[str, Any]]:
        """Return all employees."""
        pass

    @abstractmethod
    def get_policy(self, policy_name: str) -> Optional[Dict[str, Any]]:
        """Return company policy details."""
        pass

    @abstractmethod
    def get_department_contact(self, department: str) -> Optional[Dict[str, Any]]:
        """Return department contact details."""
        pass


class SQLiteDatabase(BaseDatabase):
    """SQLite implementation of BaseDatabase."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("SQLITE_DB_PATH", "app.db")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    role TEXT,
                    status TEXT,
                    department TEXT,
                    manager_id INTEGER,
                    leave_balance INTEGER,
                    FOREIGN KEY (manager_id) REFERENCES employees(id)
                )
            """)

            cursor.execute("PRAGMA table_info(employees)")
            employee_columns = {column[1] for column in cursor.fetchall()}
            if "department" not in employee_columns:
                cursor.execute("ALTER TABLE employees ADD COLUMN department TEXT")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_name TEXT UNIQUE,
                    description TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS departments (
                    department TEXT PRIMARY KEY,
                    contact_name TEXT,
                    email TEXT
                )
            """)
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM employees")
            if cursor.fetchone()[0] == 0:
                self.seed_data()

    def seed_data(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM employees")
            cursor.execute("DELETE FROM policies")
            cursor.execute("DELETE FROM departments")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('employees', 'policies')")

            cursor.executemany("""
                INSERT OR REPLACE INTO employees
                    (id, name, role, status, department, manager_id, leave_balance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, SAMPLE_EMPLOYEES)

            cursor.executemany("""
                INSERT OR REPLACE INTO policies (policy_name, description)
                VALUES (?, ?)
            """, SAMPLE_POLICIES)

            cursor.executemany("""
                INSERT OR REPLACE INTO departments (department, contact_name, email)
                VALUES (?, ?, ?)
            """, SAMPLE_DEPARTMENTS)
            conn.commit()

    def get_employee_status(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, status FROM employees WHERE LOWER(name) = LOWER(?)", (name,))
            row = cursor.fetchone()
            if row:
                return {"name": row["name"], "status": row["status"]}
            return None

    def get_leave_balance(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, leave_balance FROM employees WHERE LOWER(name) = LOWER(?)", (name,))
            row = cursor.fetchone()
            if row:
                return {"name": row["name"], "leave_balance": row["leave_balance"]}
            return None

    def get_employee_leave_status(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT e.name, e.role, e.status, e.department, e.leave_balance, m.name AS approver
                FROM employees e
                LEFT JOIN employees m ON e.manager_id = m.id
                WHERE LOWER(e.name) = LOWER(?)
            """, (name,))
            row = cursor.fetchone()
            if row:
                return {
                    "name": row["name"],
                    "role": row["role"],
                    "status": row["status"],
                    "department": row["department"],
                    "leave_balance": row["leave_balance"],
                    "approver": row["approver"] or "Executive Level (Self-Approving)",
                }
            return None

    def get_approver(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, manager_id FROM employees WHERE LOWER(name) = LOWER(?)", (name,))
            emp = cursor.fetchone()
            if not emp:
                return None
            if not emp["manager_id"]:
                return {"employee": name, "approver": "Executive Level (Self-Approving / CEO)"}

            cursor.execute("SELECT name FROM employees WHERE id = ?", (emp["manager_id"],))
            manager = cursor.fetchone()
            if manager:
                return {"employee": name, "approver": manager["name"]}
            return {"employee": name, "approver": "Manager not found"}

    def list_employees(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, role, status, department, leave_balance
                FROM employees
                ORDER BY name
            """)
            rows = cursor.fetchall()
            return [
                {
                    "name": row["name"],
                    "role": row["role"],
                    "status": row["status"],
                    "department": row["department"],
                    "leave_balance": row["leave_balance"],
                }
                for row in rows
            ]

    def get_policy(self, policy_name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT policy_name, description FROM policies WHERE LOWER(policy_name) = LOWER(?)", (policy_name,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT policy_name, description FROM policies WHERE LOWER(policy_name) LIKE LOWER(?)", (f"%{policy_name}%",))
                row = cursor.fetchone()
            if row:
                return {"policy_name": row["policy_name"], "description": row["description"]}
            return None

    def get_department_contact(self, department: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT department, contact_name, email FROM departments WHERE LOWER(department) = LOWER(?)", (department,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT department, contact_name, email FROM departments WHERE LOWER(department) LIKE LOWER(?)", (f"%{department}%",))
                row = cursor.fetchone()
            if row:
                return {
                    "department": row["department"],
                    "contact_name": row["contact_name"],
                    "email": row["email"],
                }
            return None


class MySQLDatabase(BaseDatabase):
    """MySQL implementation of BaseDatabase."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {
            "host": os.getenv("MYSQL_HOST", "10.143.89.228"),
            "user": os.getenv("MYSQL_USER", "hr_user"),
            "password": os.getenv("MYSQL_PASSWORD", "Password@123"),
            "database": os.getenv("MYSQL_DATABASE", "hr_db"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
        }

    def _get_connection(self):
        return pymysql.connect(**self.config)

    def init_db(self) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS employees (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) UNIQUE,
                        role VARCHAR(100),
                        status VARCHAR(50),
                        department VARCHAR(100),
                        manager_id INT,
                        leave_balance INT,
                        FOREIGN KEY (manager_id) REFERENCES employees(id)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS policies (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        policy_name VARCHAR(100) UNIQUE,
                        description TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS departments (
                        department VARCHAR(100) PRIMARY KEY,
                        contact_name VARCHAR(100),
                        email VARCHAR(100)
                    )
                """)
                cursor.execute("SELECT COUNT(*) as count FROM employees")
                row = cursor.fetchone()
                if row and row["count"] == 0:
                    self.seed_data()
        finally:
            conn.close()

    def seed_data(self) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                cursor.execute("DELETE FROM employees")
                cursor.execute("DELETE FROM policies")
                cursor.execute("DELETE FROM departments")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

                cursor.executemany("""
                    INSERT INTO employees (id, name, role, status, department, manager_id, leave_balance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, SAMPLE_EMPLOYEES)

                cursor.executemany("""
                    INSERT INTO policies (policy_name, description)
                    VALUES (%s, %s)
                """, SAMPLE_POLICIES)

                cursor.executemany("""
                    INSERT INTO departments (department, contact_name, email)
                    VALUES (%s, %s, %s)
                """, SAMPLE_DEPARTMENTS)
        finally:
            conn.close()

    def get_employee_status(self, name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name, status FROM employees WHERE LOWER(name) = LOWER(%s)", (name,))
                row = cursor.fetchone()
                if row:
                    return {"name": row["name"], "status": row["status"]}
                return None
        finally:
            conn.close()

    def get_leave_balance(self, name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name, leave_balance FROM employees WHERE LOWER(name) = LOWER(%s)", (name,))
                row = cursor.fetchone()
                if row:
                    return {"name": row["name"], "leave_balance": row["leave_balance"]}
                return None
        finally:
            conn.close()

    def get_employee_leave_status(self, name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT e.name, e.role, e.status, e.department, e.leave_balance, m.name AS approver
                    FROM employees e
                    LEFT JOIN employees m ON e.manager_id = m.id
                    WHERE LOWER(e.name) = LOWER(%s)
                """, (name,))
                row = cursor.fetchone()
                if row:
                    return {
                        "name": row["name"],
                        "role": row["role"],
                        "status": row["status"],
                        "department": row["department"],
                        "leave_balance": row["leave_balance"],
                        "approver": row["approver"] or "Executive Level (Self-Approving)",
                    }
                return None
        finally:
            conn.close()

    def get_approver(self, name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, manager_id FROM employees WHERE LOWER(name) = LOWER(%s)", (name,))
                emp = cursor.fetchone()
                if not emp:
                    return None
                if not emp["manager_id"]:
                    return {"employee": name, "approver": "Executive Level (Self-Approving / CEO)"}

                cursor.execute("SELECT name FROM employees WHERE id = %s", (emp["manager_id"],))
                manager = cursor.fetchone()
                if manager:
                    return {"employee": name, "approver": manager["name"]}
                return {"employee": name, "approver": "Manager not found"}
        finally:
            conn.close()

    def list_employees(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT name, role, status, department, leave_balance
                    FROM employees
                    ORDER BY name
                """)
                return cursor.fetchall()
        finally:
            conn.close()

    def get_policy(self, policy_name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT policy_name, description FROM policies WHERE LOWER(policy_name) = LOWER(%s)", (policy_name,))
                row = cursor.fetchone()
                if not row:
                    cursor.execute("SELECT policy_name, description FROM policies WHERE LOWER(policy_name) LIKE LOWER(%s)", (f"%{policy_name}%",))
                    row = cursor.fetchone()
                if row:
                    return {"policy_name": row["policy_name"], "description": row["description"]}
                return None
        finally:
            conn.close()

    def get_department_contact(self, department: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT department, contact_name, email FROM departments WHERE LOWER(department) = LOWER(%s)", (department,))
                row = cursor.fetchone()
                if not row:
                    cursor.execute("SELECT department, contact_name, email FROM departments WHERE LOWER(department) LIKE LOWER(%s)", (f"%{department}%",))
                    row = cursor.fetchone()
                if row:
                    return {
                        "department": row["department"],
                        "contact_name": row["contact_name"],
                        "email": row["email"],
                    }
                return None
        finally:
            conn.close()


def get_db(backend_type: Optional[str] = None) -> BaseDatabase:
    """Factory to retrieve database instance based on configuration."""
    backend = (backend_type or os.getenv("DB_BACKEND", "sqlite")).lower().strip()
    if backend == "mysql":
        db = MySQLDatabase()
    else:
        db = SQLiteDatabase()
    return db
