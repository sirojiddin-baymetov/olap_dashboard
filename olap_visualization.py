import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import datetime
import numpy as np
import os

# Hide the menu button
st.set_page_config(
    page_title="OLAP Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None
)

# Hide Streamlit style
hide_st_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

def create_db_connection():
    """
    Create database connection using environment variables
    """
    try:
        # Get database credentials from environment variables
        db_user = os.getenv('DB_USER', 'postgres')
        db_password = os.getenv('DB_PASSWORD', '531')
        db_host = os.getenv('DB_HOST', 'localhost')
        db_name = os.getenv('DB_NAME', 'dwh_cw_001443')
        db_port = os.getenv('DB_PORT', '5432')

        # Create connection string
        connection_string = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
        
        # Create engine
        engine = create_engine(connection_string)
        return engine
    except Exception as e:
        st.error(f"Error connecting to database: {str(e)}")
        return None

def load_data_from_dwh():
    """Load data from data warehouse tables"""
    try:
        engine = create_db_connection()
        if engine is None:
            return None, None, None, None

        # Load dimension tables
        dim_cars = pd.read_sql("SELECT * FROM dm.dim_cars", engine)
        dim_customers = pd.read_sql("SELECT * FROM dm.dim_customers", engine)
        dim_employees = pd.read_sql("SELECT * FROM dm.dim_employees", engine)
        
        # Load fact table with correct column aliases
        fact_sales = pd.read_sql("""
            SELECT 
                f.ORDER_NUMBER,
                f.ORDER_DATE,
                f.QUANTITY,
                f.TOTAL_SUM_USD,
                f.TOTAL_SUM_EUR,
                c.MODEL_NAME,
                c.CATEGORY_NAME,
                c.STATUS as CAR_STATUS,
                c.CAR_PRICE,
                cu.CUS_BUS_NAME,
                cu.CITY_NAME,
                cu.COUNTRY_NAME,
                e.FIRST_NAME as EMPLOYEE_FIRST_NAME,
                e.LAST_NAME as EMPLOYEE_LAST_NAME
            FROM dm.fct_sales_dd f
            JOIN dm.dim_cars c ON f.CAR_SURR_ID = c.CAR_SURR_ID
            JOIN dm.dim_customers cu ON f.CUSTOMER_SURR_ID = cu.CUSTOMER_SURR_ID
            JOIN dm.dim_employees e ON f.EMPLOYEE_SURR_ID = e.EMPLOYEE_SURR_ID
        """, engine)

        # Print column names for debugging
        print("Available columns in fact_sales:", fact_sales.columns.tolist())

        return dim_cars, dim_customers, dim_employees, fact_sales
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return None, None, None, None

def olap_visualization():
    """
    Main function to create and display OLAP operations dashboard
    """
    # Add custom CSS for better appearance
    st.markdown("""
        <style>
        .main {
            padding: 2rem;
        }
        .stButton>button {
            width: 100%;
            margin-top: 1rem;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("📊 OLAP Operations Dashboard")

    # Load data
    with st.spinner('Loading data from database...'):
        dim_cars, dim_customers, dim_employees, fact_sales = load_data_from_dwh()
        if any(x is None for x in [dim_cars, dim_customers, dim_employees, fact_sales]):
            st.error("Failed to load data. Please check your database connection and try again.")
            return

    # Sidebar for OLAP operation selection
    st.sidebar.title("OLAP Operations")
    operation = st.sidebar.selectbox(
        "Select OLAP Operation",
        ["Dicing", "Drill-Down", "Roll-Up", "Slicing"]
    )

    if operation == "Dicing":
        st.header("🎲 Dicing Operation")
        st.write("""
        Dicing: Selecting multiple values for multiple dimensions to create a sub-cube.
        Here we'll analyze total sales by customers' country and car category.
        """)
        
        # Group by country and category, calculate total sales and quantity
        country_category_sales = fact_sales.groupby(['country_name', 'category_name']).agg({
            'total_sum_usd': 'sum',
            'quantity': 'sum'
        }).reset_index()
        
        # Create treemap visualization
        fig = px.treemap(country_category_sales,
                        path=['country_name', 'category_name'],
                        values='total_sum_usd',
                        color='total_sum_usd',
                        color_continuous_scale='Viridis',
                        title='Total Sales by Country and Car Category',
                        custom_data=['quantity', 'total_sum_usd'])
        
        # Calculate total sales by country for percentage calculation
        country_totals = country_category_sales.groupby('country_name')['total_sum_usd'].sum()
        
        # Update hover template and add text inside boxes
        fig.update_traces(
            hovertemplate="<br>".join([
                "Country: %{label}",
                "Category: %{customdata[0]}",
                "Total Sales: $%{customdata[1]:,.2f}",
                "Quantity Sold: %{customdata[2]:,}"
            ]),
            texttemplate="%{label}<br>$%{value:,.0f}<br>(%{percentParent:.1%})",
            textposition="middle center",
            textfont=dict(size=14)
        )
        
        # Update layout for better readability
        fig.update_layout(
            margin=dict(t=50, l=25, r=25, b=25),
            uniformtext=dict(minsize=12, mode='hide'),
            font=dict(size=14)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Add detailed table
        st.subheader("Detailed Sales by Country and Category")
        st.dataframe(country_category_sales)
        
        # Add summary statistics
        st.subheader("Summary Statistics")
        
        # Calculate top performing combinations
        top_combinations = country_category_sales.nlargest(5, 'total_sum_usd')
        
        # Display top combinations
        st.write("Top 5 Country-Category Combinations by Sales:")
        for idx, row in top_combinations.iterrows():
            st.write(f"📍 {row['country_name']} - {row['category_name']}:")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Sales", f"${row['total_sum_usd']:,.2f}")
            with col2:
                st.metric("Units Sold", f"{row['quantity']:,}")

    elif operation == "Drill-Down":
        st.header("🔍 Drill-Down Operation")
        st.write("""
        Drill-Down: Moving from a higher level to a lower level of detail.
        Here we'll drill down from country to city level.
        """)
        
        # Create drill-down visualization
        country_sales = fact_sales.groupby('country_name')['total_sum_usd'].sum().reset_index()
        city_sales = fact_sales.groupby(['country_name', 'city_name'])['total_sum_usd'].sum().reset_index()
        
        # Create sunburst chart for drill-down
        fig = px.sunburst(city_sales, 
                         path=['country_name', 'city_name'], 
                         values='total_sum_usd',
                         title='Sales Drill-Down: Country to City')
        st.plotly_chart(fig, use_container_width=True)

        # Add detailed tables
        st.subheader("Country Level Sales")
        st.dataframe(country_sales)
        st.subheader("City Level Sales")
        st.dataframe(city_sales)

    elif operation == "Roll-Up":
        st.header("📈 Roll-Up Operation")
        st.write("""
        Roll-Up: Moving from a lower level to a higher level of detail.
        Here we'll roll up from daily sales to monthly, quarterly, and yearly totals.
        """)
        
        # Create roll-up visualization
        try:
            # Convert order_date to datetime
            fact_sales['order_date'] = pd.to_datetime(fact_sales['order_date'])
            
            # Extract different time periods
            fact_sales['year'] = fact_sales['order_date'].dt.year
            fact_sales['quarter'] = fact_sales['order_date'].dt.quarter
            fact_sales['month'] = fact_sales['order_date'].dt.month
            fact_sales['day'] = fact_sales['order_date'].dt.day
            fact_sales['year_quarter'] = fact_sales['year'].astype(str) + ' Q' + fact_sales['quarter'].astype(str)
            fact_sales['year_month'] = fact_sales['order_date'].dt.strftime('%Y-%m')
            fact_sales['date'] = fact_sales['order_date'].dt.strftime('%Y-%m-%d')
            
            # Create time period selector
            time_period = st.radio(
                "Select Time Period:",
                ["Monthly", "Quarterly", "Yearly"],
                horizontal=True
            )
            
            # Aggregate data based on selected time period
            if time_period == "Monthly":
                period_data = fact_sales.groupby('year_month').agg({
                    'total_sum_usd': 'sum',
                    'quantity': 'sum'
                }).reset_index()
                period_data['period'] = pd.to_datetime(period_data['year_month'] + '-01')
                x_axis = 'year_month'
                title = 'Monthly Sales Trend'
            elif time_period == "Quarterly":
                period_data = fact_sales.groupby('year_quarter').agg({
                    'total_sum_usd': 'sum',
                    'quantity': 'sum'
                }).reset_index()
                period_data['period'] = pd.to_datetime(period_data['year_quarter'].str.replace(' Q', '-Q'))
                x_axis = 'year_quarter'
                title = 'Quarterly Sales Trend'
            else:  # Yearly
                period_data = fact_sales.groupby('year').agg({
                    'total_sum_usd': 'sum',
                    'quantity': 'sum'
                }).reset_index()
                period_data['period'] = pd.to_datetime(period_data['year'].astype(str) + '-01-01')
                x_axis = 'year'
                title = 'Yearly Sales Trend'
            
            # Sort data by period
            period_data = period_data.sort_values('period')
            
            # Create line chart
            fig = go.Figure()
            
            # Add sales line
            fig.add_trace(go.Scatter(
                x=period_data[x_axis],
                y=period_data['total_sum_usd'],
                mode='lines+markers',
                name='Total Sales (USD)',
                line=dict(color='#1f77b4', width=2),
                marker=dict(size=8),
                hovertemplate="<br>".join([
                    f"{time_period}: %{{x}}",
                    "Sales: $%{y:,.2f}",
                    "<extra></extra>"
                ])
            ))
            
            # Add quantity line
            fig.add_trace(go.Scatter(
                x=period_data[x_axis],
                y=period_data['quantity'],
                mode='lines+markers',
                name='Quantity Sold',
                line=dict(color='#ff7f0e', width=2),
                marker=dict(size=8),
                yaxis='y2',
                hovertemplate="<br>".join([
                    f"{time_period}: %{{x}}",
                    "Quantity: %{y:,}",
                    "<extra></extra>"
                ])
            ))
            
            # Update layout
            fig.update_layout(
                title=title,
                xaxis_title=time_period,
                yaxis_title='Total Sales (USD)',
                yaxis2=dict(
                    title='Quantity Sold',
                    overlaying='y',
                    side='right'
                ),
                hovermode='x unified',
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Display detailed information
            st.subheader("Detailed Sales Information")
            
            # Show data table
            st.dataframe(period_data)
            
            # Add summary statistics
            st.subheader("Summary Statistics")
            
            # Calculate metrics
            total_sales = period_data['total_sum_usd'].sum()
            total_quantity = period_data['quantity'].sum()
            avg_sales = period_data['total_sum_usd'].mean()
            avg_quantity = period_data['quantity'].mean()
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Revenue", f"${total_sales:,.2f}")
            with col2:
                st.metric("Total Units Sold", f"{total_quantity:,}")
            with col3:
                st.metric(f"Average {time_period} Revenue", f"${avg_sales:,.2f}")
            with col4:
                st.metric(f"Average {time_period} Units", f"{avg_quantity:,.1f}")
            
        except Exception as e:
            st.error(f"Error in Roll-Up operation: {str(e)}")

    elif operation == "Slicing":
        st.header("🔪 Slicing Operation")
        st.write("""
        Slicing: Selecting a specific subset of data from one dimension.
        Here we'll analyze the top-3 employees by total sales performance.
        """)
        
        # Group by employee and calculate total sales and quantity
        employee_sales = fact_sales.groupby(['employee_first_name', 'employee_last_name']).agg({
            'total_sum_usd': 'sum',
            'quantity': 'sum',
            'order_number': 'count'
        }).reset_index()
        
        # Create full name column
        employee_sales['employee_name'] = employee_sales['employee_first_name'] + ' ' + employee_sales['employee_last_name']
        
        # Get top 3 employees
        top_employees = employee_sales.nlargest(3, 'total_sum_usd')
        
        # Create bar chart for top 3 employees
        fig = px.bar(
            top_employees,
            x='employee_name',
            y='total_sum_usd',
            color='total_sum_usd',
            color_continuous_scale='Viridis',
            title='Top 3 Employees by Total Sales',
            text='total_sum_usd',
            labels={'employee_name': 'Employee', 'total_sum_usd': 'Total Sales (USD)'}
        )
        
        # Update bar chart layout
        fig.update_traces(
            texttemplate='$%{text:,.0f}',
            textposition='outside',
            hovertemplate="<br>".join([
                "Employee: %{x}",
                "Total Sales: $%{y:,.2f}",
                "Orders: %{customdata[0]:,}",
                "Units Sold: %{customdata[1]:,}"
            ]),
            customdata=top_employees[['order_number', 'quantity']].values
        )
        
        # Update layout
        fig.update_layout(
            yaxis_title='Total Sales (USD)',
            showlegend=False,
            uniformtext_minsize=12,
            uniformtext_mode='hide'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display detailed information
        st.subheader("Top 3 Employees Performance")
        
        # Create columns for metrics
        for idx, row in top_employees.iterrows():
            st.write(f"### {row['employee_name']}")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Sales", f"${row['total_sum_usd']:,.2f}")
            with col2:
                st.metric("Total Orders", f"{row['order_number']:,}")
            with col3:
                st.metric("Units Sold", f"{row['quantity']:,}")
            
            # Show sales breakdown by category for each employee
            employee_categories = fact_sales[
                (fact_sales['employee_first_name'] == row['employee_first_name']) & 
                (fact_sales['employee_last_name'] == row['employee_last_name'])
            ].groupby('category_name').agg({
                'total_sum_usd': 'sum',
                'quantity': 'sum'
            }).reset_index()
            
            # Create pie chart for category distribution
            fig_category = px.pie(
                employee_categories,
                values='total_sum_usd',
                names='category_name',
                title=f'Sales Distribution by Category - {row["employee_name"]}',
                hole=0.4
            )
            
            fig_category.update_traces(
                textposition='inside',
                textinfo='percent+label',
                hovertemplate="<br>".join([
                    "Category: %{label}",
                    "Sales: $%{value:,.2f}",
                    "Quantity: %{customdata[0]:,}"
                ]),
                customdata=employee_categories['quantity'].values
            )
            
            st.plotly_chart(fig_category, use_container_width=True)
        
        # Show complete employee ranking
        st.subheader("Complete Employee Ranking")
        st.dataframe(
            employee_sales.sort_values('total_sum_usd', ascending=False)
            .style.format({
                'total_sum_usd': '${:,.2f}',
                'quantity': '{:,.0f}',
                'order_number': '{:,.0f}'
            })
        )

if __name__ == "__main__":
    # Run the Streamlit app
    olap_visualization() 
