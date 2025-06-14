import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import time
import os
from typing import List, Dict, Any

# Page configuration
st.set_page_config(
    page_title="Payment Tracker",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection
@st.cache_resource
def init_connection():
    """Initialize database connection to Neon"""
    try:
        connection = psycopg2.connect(
            host=os.getenv("NEON_HOST"),
            database=os.getenv("NEON_DATABASE"),
            user=os.getenv("NEON_USER"),
            password=os.getenv("NEON_PASSWORD"),
            port=os.getenv("NEON_PORT", "5432"),
            sslmode="require"
        )
        return connection
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

def get_payments(conn, limit: int = 100) -> List[Dict[Any, Any]]:
    """Fetch recent payments from database"""
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        query = """
        SELECT id, customer_name, amount, currency, status, payment_method, 
               created_at, updated_at
        FROM payments 
        ORDER BY created_at DESC 
        LIMIT %s
        """
        cursor.execute(query, (limit,))
        columns = [desc[0] for desc in cursor.description]
        payments = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        return payments
    except Exception as e:
        st.error(f"Error fetching payments: {e}")
        return []

def add_payment(conn, customer_name: str, amount: float, currency: str, 
                payment_method: str) -> bool:
    """Add a new payment to the database"""
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        query = """
        INSERT INTO payments (customer_name, amount, currency, status, payment_method, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        now = datetime.now()
        cursor.execute(query, (customer_name, amount, currency, "pending", payment_method, now, now))
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        st.error(f"Error adding payment: {e}")
        return False

def update_payment_status(conn, payment_id: int, new_status: str) -> bool:
    """Update payment status"""
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        query = """
        UPDATE payments 
        SET status = %s, updated_at = %s 
        WHERE id = %s
        """
        cursor.execute(query, (new_status, datetime.now(), payment_id))
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        st.error(f"Error updating payment: {e}")
        return False

def get_payment_stats(conn) -> Dict[str, Any]:
    """Get payment statistics"""
    if not conn:
        return {}
    
    try:
        cursor = conn.cursor()
        
        # Total payments today
        today = datetime.now().date()
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(amount), 0) 
            FROM payments 
            WHERE DATE(created_at) = %s
        """, (today,))
        today_count, today_total = cursor.fetchone()
        
        # Status distribution
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM payments 
            GROUP BY status
        """)
        status_dist = dict(cursor.fetchall())
        
        # Recent activity (last hour)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM payments 
            WHERE created_at >= %s
        """, (one_hour_ago,))
        recent_count = cursor.fetchone()[0]
        
        cursor.close()
        
        return {
            "today_count": today_count or 0,
            "today_total": float(today_total or 0),
            "status_distribution": status_dist,
            "recent_activity": recent_count or 0
        }
    except Exception as e:
        st.error(f"Error fetching stats: {e}")
        return {}

# Main app
def main():
    st.title("💳 Payment Tracker")
    st.markdown("Real-time payment monitoring and management")
    
    # Initialize database connection
    conn = init_connection()
    
    if not conn:
        st.error("Unable to connect to database. Please check your Neon configuration.")
        st.info("Make sure to set the following environment variables:")
        st.code("""
        NEON_HOST=your-neon-host
        NEON_DATABASE=your-database-name
        NEON_USER=your-username
        NEON_PASSWORD=your-password
        NEON_PORT=5432
        """)
        return
    
    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        
        # Auto-refresh toggle
        auto_refresh = st.checkbox("Auto Refresh", value=True)
        if auto_refresh:
            refresh_interval = st.slider("Refresh Interval (seconds)", 5, 60, 10)
        
        st.divider()
        
        # Add new payment form
        st.subheader("Add New Payment")
        with st.form("add_payment"):
            customer_name = st.text_input("Customer Name")
            amount = st.number_input("Amount", min_value=0.01, step=0.01)
            currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "JPY"])
            payment_method = st.selectbox("Payment Method", 
                                        ["credit_card", "debit_card", "paypal", "bank_transfer"])
            
            if st.form_submit_button("Add Payment"):
                if customer_name and amount > 0:
                    if add_payment(conn, customer_name, amount, currency, payment_method):
                        st.success("Payment added successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to add payment")
                else:
                    st.error("Please fill in all required fields")
    
    # Main content area
    col1, col2, col3, col4 = st.columns(4)
    
    # Get statistics
    stats = get_payment_stats(conn)
    
    with col1:
        st.metric("Today's Payments", stats.get("today_count", 0))
    
    with col2:
        st.metric("Today's Total", f"${stats.get('today_total', 0):.2f}")
    
    with col3:
        st.metric("Recent Activity (1h)", stats.get("recent_activity", 0))
    
    with col4:
        pending_count = stats.get("status_distribution", {}).get("pending", 0)
        st.metric("Pending Payments", pending_count)
    
    st.divider()
    
    # Payment status distribution
    if stats.get("status_distribution"):
        st.subheader("Payment Status Distribution")
        status_df = pd.DataFrame(
            list(stats["status_distribution"].items()),
            columns=["Status", "Count"]
        )
        st.bar_chart(status_df.set_index("Status"))
    
    st.divider()
    
    # Recent payments table
    st.subheader("Recent Payments")
    
    payments = get_payments(conn, 50)
    
    if payments:
        df = pd.DataFrame(payments)
        
        # Format the dataframe for better display
        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        df['amount'] = df['amount'].apply(lambda x: f"${float(x):.2f}")
        
        # Display the table
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "ID",
                "customer_name": "Customer",
                "amount": "Amount",
                "currency": "Currency",
                "status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["pending", "completed", "failed", "refunded"],
                ),
                "payment_method": "Method",
                "created_at": "Created",
            }
        )
        
        # Quick status update section
        st.subheader("Quick Status Update")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            payment_id = st.selectbox("Select Payment ID", [p['id'] for p in payments])
        
        with col2:
            new_status = st.selectbox("New Status", ["pending", "completed", "failed", "refunded"])
        
        with col3:
            if st.button("Update Status"):
                if update_payment_status(conn, payment_id, new_status):
                    st.success("Status updated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to update status")
    
    else:
        st.info("No payments found. Add some payments to get started!")
    
    # Auto-refresh functionality
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main()
