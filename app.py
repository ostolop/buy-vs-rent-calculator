import streamlit as st
import numpy as np
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go
from dataclasses import dataclass
from typing import Optional
import json
from urllib.parse import quote, unquote
import datetime
import os

# Report management functions
def save_report(settings, results, recommendation, comment):
    """Save a report to the session state"""
    if 'reports' not in st.session_state:
        st.session_state.reports = []
    
    report = {
        'id': len(st.session_state.reports),
        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'settings': settings,
        'results': results,
        'recommendation': recommendation,
        'comment': comment,
        'npv': {
            'buy': results['buy_npv'],
            'rent': results['rent_npv']
        },
        'final_balance': {
            'buy': results['buy_bank_balance'][-1],
            'rent': results['rent_bank_balance'][-1]
        }
    }
    
    st.session_state.reports.append(report)
    return report['id']

def load_report(report_id):
    """Load a report from the session state"""
    if 'reports' not in st.session_state:
        return None
    
    for report in st.session_state.reports:
        if report['id'] == report_id:
            return report
    return None

def delete_report(report_id):
    """Delete a report from the session state"""
    if 'reports' not in st.session_state:
        return
    
    st.session_state.reports = [r for r in st.session_state.reports if r['id'] != report_id]

# Default settings
DEFAULT_SETTINGS = {
    'property_value': 300000.0,
    'is_second_home': False,
    'deposit_type': 'Percentage',
    'deposit_percentage': 20,
    'deposit_amount': 60000.0,
    'mortgage_rate': 4.5,
    'loan_term': 25,
    'conveyancing_fees': 1500.0,
    'selling_agent_fees': 1.5,
    'home_insurance': 300.0,
    'upfront_renovation': 5000.0,
    'upfront_furniture': 3000.0,
    'home_appreciation': 3.0,
    'investment_return': 7.0,
    'include_rental': False,
    'room_rent': 500.0,
    'room_rent_increase': 3.0,
    'months_rented': 9,
    'monthly_rent': 1200.0,
    'rent_increase': 3.0,
    'utilities': 150.0,
    'sell_after': 5,
    'child_years': 3
}

def load_url_params():
    """Load settings from URL parameters"""
    # Get settings from URL parameters
    if 'settings' in st.query_params:
        try:
            # Decode the JSON string from the URL
            settings_json = unquote(st.query_params['settings'])
            return json.loads(settings_json)
        except:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_url_params(settings):
    """Save settings to URL parameters"""
    # Encode settings as JSON string in URL
    settings_json = quote(json.dumps(settings))
    st.query_params['settings'] = settings_json

def initialize_session_state():
    """Initialize session state with settings from URL parameters"""
    settings = load_url_params()
    for key, value in settings.items():
        if key not in st.session_state:
            st.session_state[key] = value

def reset_to_defaults():
    """Reset all settings to default values"""
    for key, value in DEFAULT_SETTINGS.items():
        st.session_state[key] = value
    save_url_params(DEFAULT_SETTINGS)

def update_url_from_session():
    """Update URL parameters from current session state"""
    settings = {key: st.session_state[key] for key in DEFAULT_SETTINGS.keys()}
    save_url_params(settings)

# Data classes for input parameters
@dataclass
class BuyScenario:
    mortgage_rate: float
    loan_term: int
    deposit: float
    conveyancing_fees: float
    property_value: float
    stamp_duty: float
    selling_agent_fees_percent: float
    home_appreciation_rate: float
    investment_return_rate: float
    upfront_renovation_cost: float
    upfront_furniture_cost: float
    home_insurance: float
    room_rent: Optional[float] = None
    room_rent_increase: Optional[float] = None
    months_rented_per_year: Optional[int] = None
    loan_amount: float = 0  # Will be computed
    is_second_home: bool = False
    cgt_rate: float = 0.28

@dataclass
class RentScenario:
    rent_per_month: float
    rent_annual_increase: float

@dataclass
class CommonParams:
    utilities_per_month: float
    sell_after_years: int
    child_living_years: int

def calculate_mortgage_payment(principal, annual_rate, years):
    monthly_rate = annual_rate / 12
    num_payments = years * 12
    return principal * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)

def calculate_stamp_duty(property_value: float, is_second_home: bool = False) -> float:
    if is_second_home:
        bands = [
            (0, 125000, 0.05),
            (125001, 250000, 0.07),
            (250001, float('inf'), 0.10)
        ]
    else:
        bands = [
            (0, 250000, 0),
            (250001, 925000, 0.05),
            (925001, 1500000, 0.10),
            (1500001, float('inf'), 0.12)
        ]
    
    duty = 0
    for lower, upper, rate in bands:
        if property_value > lower:
            taxable = min(property_value - lower, upper - lower)
            duty += taxable * rate
    return duty

def calculate_cash_flows(buy: BuyScenario, rent: RentScenario, common: CommonParams):
    years = np.arange(0, common.sell_after_years + 1)
    
    # Buy scenario calculations
    monthly_mortgage = calculate_mortgage_payment(
        buy.loan_amount,
        buy.mortgage_rate,
        buy.loan_term
    )
    
    # Initialize arrays
    buy_cash_flow = np.zeros_like(years, dtype=float)
    property_value = np.zeros_like(years, dtype=float)
    mortgage_balance = np.zeros_like(years, dtype=float)
    accumulated_equity = np.zeros_like(years, dtype=float)
    buy_bank_balance = np.zeros_like(years, dtype=float)
    buy_yearly_details = []  # Store detailed breakdown for each year
    
    # Initial costs (Year 0)
    initial_costs = {
        "deposit": -buy.deposit,
        "conveyancing_fees": -buy.conveyancing_fees,
        "stamp_duty": -buy.stamp_duty,
        "upfront_renovation": -buy.upfront_renovation_cost,
        "upfront_furniture": -buy.upfront_furniture_cost
    }
    
    buy_cash_flow[0] = sum(initial_costs.values())
    buy_bank_balance[0] = 0  # Start at 0 after paying all initial costs
    property_value[0] = buy.property_value
    mortgage_balance[0] = buy.loan_amount
    accumulated_equity[0] = buy.deposit
    
    # Add year 0 details
    buy_yearly_details.append({
        "year": 0,
        "cash_flow": buy_cash_flow[0],
        "property_value": property_value[0],
        "mortgage_balance": mortgage_balance[0],
        "equity": accumulated_equity[0],
        "components": initial_costs,
        "bank_balance": buy_bank_balance[0]
    })
    
    # Calculate yearly cash flows
    for i in range(1, len(years)):
        yearly_components = {}
        
        # Property appreciation
        property_value[i] = property_value[i-1] * (1 + buy.home_appreciation_rate)
        yearly_components["property_appreciation"] = property_value[i] - property_value[i-1]
        
        # Mortgage payments
        yearly_mortgage = monthly_mortgage * 12
        interest_payment = mortgage_balance[i-1] * buy.mortgage_rate
        principal_payment = yearly_mortgage - interest_payment
        mortgage_balance[i] = mortgage_balance[i-1] - principal_payment
        accumulated_equity[i] = accumulated_equity[i-1] + principal_payment
        buy_cash_flow[i] -= yearly_mortgage
        yearly_components["mortgage_payment"] = -yearly_mortgage
        yearly_components["interest_paid"] = -interest_payment
        yearly_components["principal_paid"] = -principal_payment
        
        # Insurance and utilities
        buy_cash_flow[i] -= buy.home_insurance
        buy_cash_flow[i] -= common.utilities_per_month * 12
        yearly_components["insurance"] = -buy.home_insurance
        yearly_components["utilities"] = -common.utilities_per_month * 12
        
        # Room rental income
        if buy.room_rent is not None and buy.room_rent_increase is not None and buy.months_rented_per_year is not None:
            if i <= common.child_living_years:
                room_rent = buy.room_rent * (1 + buy.room_rent_increase) ** (i-1)
                room_rent_income = room_rent * buy.months_rented_per_year
                buy_cash_flow[i] += room_rent_income
                yearly_components["rental_income"] = room_rent_income
            else:
                room_rent = buy.room_rent * (1 + buy.room_rent_increase) ** (i-1)
                full_rent_income = room_rent * 12 * 2  # Full house rental
                buy_cash_flow[i] += full_rent_income
                yearly_components["rental_income"] = full_rent_income
        
        buy_bank_balance[i] = buy_bank_balance[i-1] + buy_cash_flow[i]
        
        # Add yearly details
        buy_yearly_details.append({
            "year": i,
            "cash_flow": buy_cash_flow[i],
            "property_value": property_value[i],
            "mortgage_balance": mortgage_balance[i],
            "equity": property_value[i] - mortgage_balance[i],
            "components": yearly_components,
            "bank_balance": buy_bank_balance[i]
        })
    
    # Add the final property sale to the last year's cash flow
    final_year = common.sell_after_years
    selling_price = property_value[final_year]
    agent_fees = selling_price * buy.selling_agent_fees_percent
    remaining_mortgage = mortgage_balance[final_year]
    
    # Calculate capital gains tax
    original_cost = buy.property_value + buy.conveyancing_fees + buy.stamp_duty
    
    # Calculate total mortgage interest paid over the years
    total_mortgage_interest = 0
    for i in range(common.sell_after_years + 1):  # Include the selling year
        yearly_mortgage = monthly_mortgage * 12
        interest_payment = mortgage_balance[i] * buy.mortgage_rate
        total_mortgage_interest += interest_payment
    
    # Calculate mortgage interest deduction (20% of total mortgage interest)
    mortgage_interest_deduction = total_mortgage_interest * 0.20
    
    # Calculate taxable gain after mortgage interest deduction
    capital_gain = selling_price - original_cost
    taxable_gain = max(0, capital_gain - mortgage_interest_deduction)
    
    # Only apply CGT if it's a second home
    cgt = taxable_gain * buy.cgt_rate if (taxable_gain > 0 and buy.is_second_home) else 0
    
    # Calculate sale proceeds (this is what you actually get in your bank account)
    sale_proceeds = selling_price - agent_fees - remaining_mortgage - cgt
    
    # Debug logging
    print(f"Original cost: £{original_cost:,.2f}")
    print(f"Total mortgage interest: £{total_mortgage_interest:,.2f}")
    print(f"Mortgage interest deduction: £{mortgage_interest_deduction:,.2f}")
    print(f"Capital gain: £{capital_gain:,.2f}")
    print(f"Taxable gain: £{taxable_gain:,.2f}")
    print(f"CGT: £{cgt:,.2f}")
    print(f"Agent fees: £{agent_fees:,.2f}")
    print(f"Remaining mortgage: £{remaining_mortgage:,.2f}")
    print(f"Final sale proceeds: £{sale_proceeds:,.2f}")
    
    # Add sale proceeds to final year cash flow
    buy_cash_flow[final_year] += sale_proceeds
    buy_bank_balance[final_year] = buy_bank_balance[final_year-1] + sale_proceeds
    
    buy_yearly_details[final_year]["components"].update({
        "property_sale": selling_price,
        "agent_fees": -agent_fees,
        "mortgage_repayment": -remaining_mortgage,
        "capital_gains_tax": -cgt,
        "mortgage_interest_deduction": mortgage_interest_deduction
    })
    buy_yearly_details[final_year]["cash_flow"] = buy_cash_flow[final_year]
    buy_yearly_details[final_year]["bank_balance"] = buy_bank_balance[final_year]
    
    # Rent scenario calculations with investment returns
    rent_cash_flow = np.zeros_like(years, dtype=float)
    rent_bank_balance = np.zeros_like(years, dtype=float)
    rent_yearly_details = []
    
    # Initial investment (deposit equivalent)
    investment_balance = buy.deposit  # Start with the same amount as deposit
    rent_bank_balance[0] = buy.deposit
    
    rent_yearly_details.append({
        "year": 0,
        "cash_flow": 0,
        "rent_paid": 0,
        "utilities": 0,
        "bank_balance": rent_bank_balance[0]
    })
    
    # Calculate rent scenario cash flows
    for i in range(1, len(years)):
        # Investment returns
        investment_return = investment_balance * buy.investment_return_rate
        rent_cash_flow[i] += investment_return
        investment_balance += investment_return  # Add returns to balance for compound interest
        
        # Rent and utilities - only for years when child is living there
        if i <= common.child_living_years:
            yearly_rent = rent.rent_per_month * 12 * (1 + rent.rent_annual_increase) ** (i-1)
            utilities_cost = common.utilities_per_month * 12
            rent_cash_flow[i] -= yearly_rent + utilities_cost
            rent_yearly_details.append({
                "year": i,
                "cash_flow": rent_cash_flow[i],
                "investment_returns": investment_return,
                "rent_paid": -yearly_rent,
                "utilities": -utilities_cost,
                "bank_balance": rent_bank_balance[i-1] + rent_cash_flow[i]  # Update bank balance with this year's cash flow
            })
        else:
            rent_yearly_details.append({
                "year": i,
                "cash_flow": rent_cash_flow[i],
                "investment_returns": investment_return,
                "rent_paid": 0,
                "utilities": 0,
                "bank_balance": rent_bank_balance[i-1] + rent_cash_flow[i]  # Update bank balance with this year's cash flow
            })
        
        # Update bank balance
        rent_bank_balance[i] = rent_bank_balance[i-1] + rent_cash_flow[i]
    
    # Calculate NPV for both scenarios
    discount_rate = buy.investment_return_rate  # Use investment return rate as discount rate
    buy_npv = npf.npv(discount_rate, buy_cash_flow)
    rent_npv = npf.npv(discount_rate, rent_cash_flow)
    
    return {
        'buy_cash_flow': buy_cash_flow,
        'rent_cash_flow': rent_cash_flow,
        'property_value': property_value,
        'mortgage_balance': mortgage_balance,
        'accumulated_equity': accumulated_equity,
        'buy_bank_balance': buy_bank_balance,
        'rent_bank_balance': rent_bank_balance,
        'years': years,
        'buy_yearly_details': buy_yearly_details,
        'rent_yearly_details': rent_yearly_details,
        'buy_npv': buy_npv,
        'rent_npv': rent_npv
    }

def generate_recommendation(results, buy: BuyScenario, rent: RentScenario, common: CommonParams) -> str:
    # Calculate final positions consistently - use only bank balance which includes everything
    final_buy_position = results['buy_bank_balance'][-1]  # This already includes sale proceeds
    final_rent_position = results['rent_bank_balance'][-1]  # This already includes investment returns
    npv_difference = results['buy_npv'] - results['rent_npv']
    
    recommendation = []
    
    # Overall financial comparison
    if final_buy_position > final_rent_position:
        difference = final_buy_position - final_rent_position
        recommendation.append(f"Buying appears to be more financially advantageous by £{difference:,.2f} after {common.sell_after_years} years.")
    else:
        difference = final_rent_position - final_buy_position
        recommendation.append(f"Renting appears to be more financially advantageous by £{difference:,.2f} after {common.sell_after_years} years.")
    
    # NPV analysis
    if npv_difference > 0:
        recommendation.append(f"\nThe Net Present Value (NPV) analysis favors buying, with a difference of £{npv_difference:,.2f} when using a discount rate of {buy.investment_return_rate*100:.1f}%.")
    else:
        recommendation.append(f"\nThe Net Present Value (NPV) analysis favors renting, with a difference of £{-npv_difference:,.2f} when using a discount rate of {buy.investment_return_rate*100:.1f}%.")
    
    # Property appreciation
    total_appreciation = results['property_value'][-1] - buy.property_value
    recommendation.append(f"\nProperty appreciation: The property value is expected to increase by £{total_appreciation:,.2f} over {common.sell_after_years} years at {buy.home_appreciation_rate*100:.1f}% annual appreciation.")
    
    # Investment returns analysis for rent scenario
    initial_deposit = buy.deposit
    final_investment = results['rent_bank_balance'][-1]
    # Calculate total investment returns by summing up all the yearly returns
    total_investment_returns = sum(detail.get('investment_returns', 0) for detail in results['rent_yearly_details'])
    recommendation.append(f"\nInvestment returns: The deposit of £{initial_deposit:,.2f} would generate £{total_investment_returns:,.2f} in investment returns at {buy.investment_return_rate*100:.1f}% annual return.")
    
    # Rental income analysis
    if buy.room_rent is not None:
        total_rental_income = sum(detail['components'].get('rental_income', 0) for detail in results['buy_yearly_details'])
        recommendation.append(f"\nRental income: Expected to generate £{total_rental_income:,.2f} in total rental income over the period.")
    
    # Initial costs vs long-term benefits
    initial_costs = -results['buy_cash_flow'][0]
    recommendation.append(f"\nInitial costs: The total upfront cost of £{initial_costs:,.2f} includes deposit (£{buy.deposit:,.2f}), stamp duty (£{buy.stamp_duty:,.2f}), and other fees.")
    
    # Mortgage analysis
    total_interest = sum(abs(detail['components'].get('interest_paid', 0)) for detail in results['buy_yearly_details'][1:])
    recommendation.append(f"\nMortgage costs: Total interest paid over the period would be £{total_interest:,.2f} at {buy.mortgage_rate*100:.1f}% interest rate.")
    
    return "\n".join(recommendation)

def plot_cash_flows(results):
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=results['years'],
        y=results['buy_bank_balance'],
        name='Buy Scenario Balance',
        line=dict(color='blue')
    ))
    
    fig.add_trace(go.Scatter(
        x=results['years'],
        y=results['rent_bank_balance'],
        name='Rent Scenario Balance',
        line=dict(color='red')
    ))
    
    fig.update_layout(
        title='Cash Flow Comparison: Buy vs Rent',
        xaxis_title='Years',
        yaxis_title='Balance (£)',
        showlegend=True
    )
    
    return fig

def main():
    st.title('Student Accommodation Rent vs Buy Calculator')
    
    # About section
    with st.expander("About this Calculator"):
        st.markdown("""
        This calculator helps parents and students make informed decisions about whether to buy or rent student accommodation. It provides a comprehensive financial comparison between purchasing a property for student housing versus renting over a specified period.

        **Key Features:**
        - Detailed mortgage calculations including interest rates and loan terms
        - Property value appreciation projections
        - Rental income potential from letting rooms
        - Complete cost analysis including stamp duty, conveyancing fees, and maintenance
        - Investment return comparisons
        - Flexible scenarios for different time periods
        - Net Present Value (NPV) analysis
        
        **How to Use:**
        1. Adjust the parameters in the sidebar to match your specific situation
        2. Review the detailed analysis and visualizations
        3. Compare the long-term financial implications of buying versus renting
        4. Use the URL sharing feature to save and share your calculations
        
        **Note:** This calculator is designed as a decision-support tool and should be used alongside professional financial advice for making property investment decisions.

        **About the Author:**
        Created by Misha Kapushesky (c) 2025

        [![GitHub](https://img.shields.io/badge/GitHub-Profile-blue?style=flat&logo=github)](https://github.com/ostolop)
        """)
    
    st.write('Compare the financial implications of renting versus buying a student accommodation property.')
    
    # Initialize session state from URL parameters
    initialize_session_state()
    
    with st.sidebar:
        st.header('Input Parameters')
        
        st.subheader('Property Details')
        property_value = st.number_input('Property Value (£)', 
            min_value=0.0, 
            value=st.session_state.property_value, 
            step=1000.0,
            key='property_value'
        )
        is_second_home = st.checkbox('Is this a second home?', 
            value=st.session_state.is_second_home,
            key='is_second_home'
        )
        
        st.subheader('Mortgage Details')
        deposit_type = st.radio('Deposit Input Type', 
            ['Percentage', 'Fixed Amount'],
            index=0 if st.session_state.deposit_type == 'Percentage' else 1,
            key='deposit_type'
        )
        
        if deposit_type == 'Percentage':
            deposit_percentage = st.number_input('Deposit Percentage (%)', 
                min_value=5.0, max_value=100.0, 
                value=float(st.session_state.deposit_percentage), 
                step=0.1,
                format="%.1f",
                key='deposit_percentage'
            )
            deposit = property_value * (deposit_percentage / 100)
        else:
            deposit = st.number_input('Deposit Amount (£)', 
                min_value=0.0, 
                value=st.session_state.deposit_amount, 
                step=1000.0,
                key='deposit_amount'
            )
        
        loan_amount = property_value - deposit
        mortgage_rate = st.number_input('Mortgage Interest Rate (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(st.session_state.mortgage_rate), 
            step=0.1,
            format="%.2f",
            key='mortgage_rate'
        ) / 100
        loan_term = st.number_input('Loan Term (years)', 
            min_value=5, max_value=35, 
            value=int(st.session_state.loan_term), 
            step=1,
            key='loan_term'
        )
        
        st.subheader('Additional Costs')
        conveyancing_fees = st.number_input('Conveyancing Fees (£)', 
            min_value=0.0, 
            value=st.session_state.conveyancing_fees, 
            step=100.0,
            key='conveyancing_fees'
        )
        selling_agent_fees = st.number_input('Selling Agent Fees (%)', 
            min_value=0.0, max_value=10.0, 
            value=float(st.session_state.selling_agent_fees), 
            step=0.1,
            format="%.2f",
            key='selling_agent_fees'
        ) / 100
        home_insurance = st.number_input('Annual Home Insurance (£)', 
            min_value=0.0, 
            value=st.session_state.home_insurance, 
            step=10.0,
            key='home_insurance'
        )
        upfront_renovation = st.number_input('Upfront Renovation Cost (£)', 
            min_value=0.0, 
            value=st.session_state.upfront_renovation, 
            step=100.0,
            key='upfront_renovation'
        )
        upfront_furniture = st.number_input('Upfront Furniture Cost (£)', 
            min_value=0.0, 
            value=st.session_state.upfront_furniture, 
            step=100.0,
            key='upfront_furniture'
        )
        
        st.subheader('Market Conditions')
        home_appreciation = st.number_input('Annual Home Appreciation Rate (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(st.session_state.home_appreciation), 
            step=0.1,
            format="%.2f",
            key='home_appreciation'
        ) / 100
        investment_return = st.number_input('Investment Return Rate (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(st.session_state.investment_return), 
            step=0.1,
            format="%.2f",
            key='investment_return'
        ) / 100
        
        st.subheader('Rental Income')
        include_rental = st.checkbox('Include Rental Income', 
            value=st.session_state.include_rental,
            key='include_rental'
        )
        room_rent = None
        room_rent_increase = None
        months_rented = None
        if include_rental:
            room_rent = st.number_input('Monthly Room Rent (£)', 
                min_value=0.0, 
                value=st.session_state.room_rent, 
                step=10.0,
                key='room_rent'
            )
            room_rent_increase = st.number_input('Annual Room Rent Increase (%)', 
                min_value=0.0, max_value=20.0, 
                value=float(st.session_state.room_rent_increase), 
                step=0.1,
                format="%.2f",
                key='room_rent_increase'
            ) / 100
            months_rented = st.number_input('Months Rented Per Year', 
                min_value=1, max_value=12, 
                value=int(st.session_state.months_rented), 
                step=1,
                key='months_rented'
            )
        
        st.subheader('Rental Scenario')
        monthly_rent = st.number_input('Monthly Rent Payment (£)', 
            min_value=0.0, 
            value=st.session_state.monthly_rent, 
            step=10.0,
            key='monthly_rent'
        )
        rent_increase = st.number_input('Annual Rent Increase (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(st.session_state.rent_increase), 
            step=0.1,
            format="%.2f",
            key='rent_increase'
        ) / 100
        
        st.subheader('Common Parameters')
        utilities = st.number_input('Monthly Utilities (£)', 
            min_value=0.0, 
            value=st.session_state.utilities, 
            step=10.0,
            key='utilities'
        )
        sell_after = st.number_input('Sell After (years)', 
            min_value=1, max_value=50, 
            value=int(st.session_state.sell_after), 
            step=1,
            key='sell_after'
        )
        child_years = st.number_input('Years Your Child Will Live In Property', 
            min_value=1, max_value=10, 
            value=int(st.session_state.child_years), 
            step=1,
            key='child_years'
        )
        
        # Add a reset button
        if st.button('Reset to Defaults'):
            reset_to_defaults()
            st.experimental_rerun()
    
    # Update URL whenever any value changes
    update_url_from_session()
    
    # Create scenario objects
    buy = BuyScenario(
        mortgage_rate=mortgage_rate,
        loan_term=loan_term,
        deposit=deposit,
        conveyancing_fees=conveyancing_fees,
        property_value=property_value,
        stamp_duty=calculate_stamp_duty(property_value, is_second_home),
        selling_agent_fees_percent=selling_agent_fees,
        home_appreciation_rate=home_appreciation,
        investment_return_rate=investment_return,
        upfront_renovation_cost=upfront_renovation,
        upfront_furniture_cost=upfront_furniture,
        home_insurance=home_insurance,
        room_rent=room_rent,
        room_rent_increase=room_rent_increase,
        months_rented_per_year=months_rented,
        loan_amount=loan_amount,
        is_second_home=is_second_home
    )
    
    rent = RentScenario(
        rent_per_month=monthly_rent,
        rent_annual_increase=rent_increase
    )
    
    common = CommonParams(
        utilities_per_month=utilities,
        sell_after_years=sell_after,
        child_living_years=child_years
    )
    
    # Calculate results
    results = calculate_cash_flows(buy, rent, common)
    
    # Display results
    st.header('Analysis Results')
    
    # Initial Summary
    st.subheader('Summary')
    final_buy_position = results['buy_bank_balance'][-1] + (results['property_value'][-1] - results['mortgage_balance'][-1])
    final_rent_position = results['rent_bank_balance'][-1]
    
    if final_buy_position > final_rent_position:
        st.success(f'Buying appears to be more financially advantageous by £{(final_buy_position - final_rent_position):,.2f}')
    else:
        st.success(f'Renting appears to be more financially advantageous by £{(final_rent_position - final_buy_position):,.2f}')
    
    # Input Parameters Table
    st.subheader('Input Parameters')
    input_params = {
        'Property Details': {
            'Property Value': f'£{property_value:,.2f}',
            'Is Second Home': 'Yes' if is_second_home else 'No',
            'Deposit Type': deposit_type,
            'Deposit Amount': f'£{deposit:,.2f}',
            'Deposit Percentage': f'{deposit_percentage if deposit_type == "Percentage" else (deposit/property_value*100):.1f}%'
        },
        'Mortgage Details': {
            'Mortgage Rate': f'{mortgage_rate*100:.2f}%',
            'Loan Term': f'{loan_term} years',
            'Loan Amount': f'£{loan_amount:,.2f}'
        },
        'Additional Costs': {
            'Conveyancing Fees': f'£{conveyancing_fees:,.2f}',
            'Selling Agent Fees': f'{selling_agent_fees*100:.1f}%',
            'Home Insurance': f'£{home_insurance:,.2f}',
            'Upfront Renovation': f'£{upfront_renovation:,.2f}',
            'Upfront Furniture': f'£{upfront_furniture:,.2f}'
        },
        'Market Conditions': {
            'Home Appreciation Rate': f'{home_appreciation*100:.1f}%',
            'Investment Return Rate': f'{investment_return*100:.1f}%'
        },
        'Rental Details': {
            'Include Rental Income': 'Yes' if include_rental else 'No',
            'Monthly Room Rent': f'£{room_rent:,.2f}' if room_rent else 'N/A',
            'Room Rent Increase': f'{room_rent_increase*100:.1f}%' if room_rent_increase else 'N/A',
            'Months Rented Per Year': f'{months_rented}' if months_rented else 'N/A',
            'Monthly Rent Payment': f'£{monthly_rent:,.2f}',
            'Annual Rent Increase': f'{rent_increase*100:.1f}%'
        },
        'Common Parameters': {
            'Monthly Utilities': f'£{utilities:,.2f}',
            'Sell After Years': f'{sell_after} years',
            'Child Living Years': f'{child_years} years'
        }
    }
    
    # Create a DataFrame for each category and display them
    for category, params in input_params.items():
        st.write(f'**{category}**')
        df = pd.DataFrame(list(params.items()), columns=['Parameter', 'Value'])
        st.dataframe(df, hide_index=True)
    
    # Cost Breakdown
    st.subheader('Cost Breakdown')
    col1, col2 = st.columns(2)
    
    with col1:
        st.write('Buy Scenario Initial Costs')
        st.write(f'• Deposit: £{deposit:,.2f}')
        st.write(f'• Stamp Duty: £{calculate_stamp_duty(property_value, is_second_home):,.2f}')
        st.write(f'• Conveyancing Fees: £{conveyancing_fees:,.2f}')
        st.write(f'• Upfront Renovation: £{upfront_renovation:,.2f}')
        st.write(f'• Upfront Furniture: £{upfront_furniture:,.2f}')
        st.write(f'**Total Initial Cost: £{-results["buy_cash_flow"][0]:,.2f}**')
    
    with col2:
        st.write('Monthly Payments')
        monthly_mortgage = calculate_mortgage_payment(loan_amount, mortgage_rate, loan_term)
        st.write(f'• Monthly Mortgage: £{monthly_mortgage:,.2f}')
        st.write(f'• Monthly Utilities: £{utilities:,.2f}')
        if include_rental:
            st.write(f'• Monthly Rental Income: £{room_rent:,.2f}')
        st.write(f'• Monthly Insurance: £{home_insurance/12:,.2f}')
    
    # NPV Analysis
    st.subheader('Net Present Value (NPV) Analysis')
    npv_col1, npv_col2 = st.columns(2)
    with npv_col1:
        st.metric('Buy Scenario NPV', f'£{results["buy_npv"]:,.2f}')
    with npv_col2:
        st.metric('Rent Scenario NPV', f'£{results["rent_npv"]:,.2f}')
    st.write(f'NPV Difference: £{(results["buy_npv"] - results["rent_npv"]):,.2f}')
    
    # Combined Cash Flow and Balance Sheet Analysis
    st.subheader('Detailed Financial Analysis')
    analysis_tab1, analysis_tab2 = st.tabs(['Buy Scenario', 'Rent Scenario'])
    
    with analysis_tab1:
        buy_df = pd.DataFrame([{
            'Year': d['year'],
            'Cash Flow': d['cash_flow'],
            'Mortgage Payment': d['components'].get('mortgage_payment', 0),
            'Interest Paid': d['components'].get('interest_paid', 0),
            'Principal Paid': d['components'].get('principal_paid', 0),
            'Rental Income': d['components'].get('rental_income', 0),
            'Insurance': d['components'].get('insurance', 0),
            'Utilities': d['components'].get('utilities', 0),
            'Property Sale': d['components'].get('property_sale', 0),
            'Agent Fees': d['components'].get('agent_fees', 0),
            'Mortgage Repayment': d['components'].get('mortgage_repayment', 0),
            'Capital Gains Tax': d['components'].get('capital_gains_tax', 0),
            'Property Value': d['property_value'],
            'Mortgage Balance': d['mortgage_balance'],
            'Equity': d['equity'],
            'Bank Balance': d['bank_balance'],
            'Net Worth': d['bank_balance']  # Always use bank balance which includes all assets and liabilities
        } for d in results['buy_yearly_details']])
        
        # Format all columns except 'Year' with currency
        buy_df_styled = buy_df.style.format({
            'Cash Flow': '£{:,.2f}',
            'Mortgage Payment': '£{:,.2f}',
            'Interest Paid': '£{:,.2f}',
            'Principal Paid': '£{:,.2f}',
            'Rental Income': '£{:,.2f}',
            'Insurance': '£{:,.2f}',
            'Utilities': '£{:,.2f}',
            'Property Sale': '£{:,.2f}',
            'Agent Fees': '£{:,.2f}',
            'Mortgage Repayment': '£{:,.2f}',
            'Capital Gains Tax': '£{:,.2f}',
            'Property Value': '£{:,.2f}',
            'Mortgage Balance': '£{:,.2f}',
            'Equity': '£{:,.2f}',
            'Bank Balance': '£{:,.2f}',
            'Net Worth': '£{:,.2f}',
            'Year': '{:.0f}'  # Format Year as integer
        })
        st.dataframe(buy_df_styled, hide_index=True)
    
    with analysis_tab2:
        rent_df = pd.DataFrame([{
            'Year': d['year'],
            'Cash Flow': d['cash_flow'],
            'Investment Returns': d.get('investment_returns', 0),
            'Rent Paid': d.get('rent_paid', 0),
            'Utilities': d.get('utilities', 0),
            'Bank Balance': d['bank_balance'],
            'Net Worth': d['bank_balance']  # For rent scenario, net worth is just the bank balance
        } for d in results['rent_yearly_details']])
        
        # Format all columns except 'Year' with currency
        rent_df_styled = rent_df.style.format({
            'Cash Flow': '£{:,.2f}',
            'Investment Returns': '£{:,.2f}',
            'Rent Paid': '£{:,.2f}',
            'Utilities': '£{:,.2f}',
            'Bank Balance': '£{:,.2f}',
            'Net Worth': '£{:,.2f}',
            'Year': '{:.0f}'  # Format Year as integer
        })
        st.dataframe(rent_df_styled, hide_index=True)
    
    # Visualization
    st.subheader('Cash Flow Comparison')
    st.plotly_chart(plot_cash_flows(results))
    
    # Detailed Analysis and Recommendation
    st.subheader('Detailed Analysis')
    recommendation = generate_recommendation(results, buy, rent, common)
    st.write(recommendation)
    
    # Final Position
    st.subheader('Final Position')
    
    # Calculate total cash inflows and outflows for both scenarios
    buy_inflows = sum(max(0, flow) for flow in results['buy_cash_flow'])
    buy_outflows = sum(min(0, flow) for flow in results['buy_cash_flow'])
    rent_inflows = sum(max(0, flow) for flow in results['rent_cash_flow'])
    rent_outflows = sum(min(0, flow) for flow in results['rent_cash_flow'])
    
    final_col1, final_col2 = st.columns(2)
    with final_col1:
        st.metric('Buy Scenario Net Worth', f'£{results["buy_bank_balance"][-1]:,.2f}')
        st.write('Cash Flow Summary:')
        st.write(f'• Total Inflows: £{buy_inflows:,.2f}')
        st.write(f'• Total Outflows: £{abs(buy_outflows):,.2f}')
        st.write(f'• Net Cash Flow: £{buy_inflows + buy_outflows:,.2f}')
    with final_col2:
        st.metric('Rent Scenario Net Worth', f'£{results["rent_bank_balance"][-1]:,.2f}')
        st.write('Cash Flow Summary:')
        st.write(f'• Total Inflows: £{rent_inflows:,.2f}')
        st.write(f'• Total Outflows: £{abs(rent_outflows):,.2f}')
        st.write(f'• Net Cash Flow: £{rent_inflows + rent_outflows:,.2f}')
    
    st.write(f'Difference: £{abs(results["buy_bank_balance"][-1] - results["rent_bank_balance"][-1]):,.2f} in favor of {"buying" if results["buy_bank_balance"][-1] > results["rent_bank_balance"][-1] else "renting"}')

    # Report Management
    st.subheader('Report Management')
    
    # Save current report
    report_comment = st.text_input('Add a comment to your report (optional)')
    if st.button('Save Current Report'):
        current_settings = {key: st.session_state[key] for key in DEFAULT_SETTINGS.keys()}
        report_id = save_report(current_settings, results, recommendation, report_comment)
        st.success(f'Report saved successfully! (ID: {report_id})')
    
    # View saved reports
    if 'reports' in st.session_state and st.session_state.reports:
        st.write('### Saved Reports')
        
        # Create a DataFrame of reports
        reports_df = pd.DataFrame([{
            'ID': report['id'],
            'Timestamp': report['timestamp'],
            'Property Value': f'£{report["settings"]["property_value"]:,.2f}',
            'Buy NPV': f'£{report["npv"]["buy"]:,.2f}',
            'Rent NPV': f'£{report["npv"]["rent"]:,.2f}',
            'Final Buy Balance': f'£{report["final_balance"]["buy"]:,.2f}',
            'Final Rent Balance': f'£{report["final_balance"]["rent"]:,.2f}',
            'Comment': report['comment']
        } for report in st.session_state.reports])
        
        # Display reports table
        st.dataframe(reports_df, hide_index=True)
        
        # Load report
        selected_report_id = st.selectbox(
            'Select a report to load',
            options=[report['id'] for report in st.session_state.reports],
            format_func=lambda x: f"Report {x} - {next(r['timestamp'] for r in st.session_state.reports if r['id'] == x)}"
        )
        
        if selected_report_id is not None:
            col1, col2 = st.columns(2)
            with col1:
                if st.button('Load Selected Report'):
                    report = load_report(selected_report_id)
                    if report:
                        # Update session state with report settings
                        for key, value in report['settings'].items():
                            st.session_state[key] = value
                        st.experimental_rerun()
            with col2:
                if st.button('Delete Selected Report'):
                    delete_report(selected_report_id)
                    st.experimental_rerun()
    else:
        st.info('No saved reports yet. Run an analysis and click "Save Current Report" to save one.')

if __name__ == '__main__':
    main() 