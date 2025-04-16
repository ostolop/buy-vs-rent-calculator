import streamlit as st
import numpy as np
import numpy_financial as npf
import pandas as pd
import plotly.graph_objects as go
from dataclasses import dataclass
from typing import Optional
import json
import os

SETTINGS_FILE = 'calculator_settings.json'

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

def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                
                # Migrate from daughter_years to child_years if needed
                if 'daughter_years' in settings and 'child_years' not in settings:
                    settings['child_years'] = settings.pop('daughter_years')
                    # Save the migrated settings
                    save_settings(settings)
                return settings
    except Exception as e:
        st.warning(f"Could not load saved settings: {str(e)}")
    return DEFAULT_SETTINGS

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        st.warning(f"Could not save settings: {str(e)}")

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
    buy_bank_balance[0] = -sum(initial_costs.values())
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
        "components": initial_costs
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
            "components": yearly_components
        })
    
    # Add the final property sale to the last year's cash flow
    final_year = common.sell_after_years
    selling_price = property_value[final_year]
    agent_fees = selling_price * buy.selling_agent_fees_percent
    remaining_mortgage = mortgage_balance[final_year]
    
    # Calculate capital gains tax
    original_cost = buy.property_value + buy.conveyancing_fees + buy.stamp_duty
    capital_gain = selling_price - original_cost
    cgt = capital_gain * buy.cgt_rate if capital_gain > 0 else 0
    
    # Add sale proceeds to final year cash flow
    sale_proceeds = selling_price - agent_fees - remaining_mortgage - cgt
    buy_cash_flow[final_year] += sale_proceeds
    buy_bank_balance[final_year] += sale_proceeds
    
    buy_yearly_details[final_year]["components"].update({
        "property_sale": selling_price,
        "agent_fees": -agent_fees,
        "mortgage_repayment": -remaining_mortgage,
        "capital_gains_tax": -cgt
    })
    buy_yearly_details[final_year]["cash_flow"] = buy_cash_flow[final_year]
    
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
        investment_balance += investment_return
        
        # Rent and utilities
        yearly_rent = rent.rent_per_month * 12 * (1 + rent.rent_annual_increase) ** (i-1)
        utilities_cost = common.utilities_per_month * 12
        rent_cash_flow[i] -= yearly_rent + utilities_cost
        
        # Update bank balance
        rent_bank_balance[i] = rent_bank_balance[i-1] + rent_cash_flow[i]
        
        rent_yearly_details.append({
            "year": i,
            "cash_flow": rent_cash_flow[i],
            "rent_paid": -yearly_rent,
            "utilities": -utilities_cost,
            "bank_balance": rent_bank_balance[i]
        })
    
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
    final_buy_position = results['buy_bank_balance'][-1] + (results['property_value'][-1] - results['mortgage_balance'][-1])
    final_rent_position = results['rent_bank_balance'][-1]
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
    st.write('Compare the financial implications of renting versus buying a student accommodation property.')
    
    # Load saved settings
    settings = load_settings()
    
    with st.sidebar:
        st.header('Input Parameters')
        
        st.subheader('Property Details')
        property_value = st.number_input('Property Value (£)', min_value=0.0, value=settings['property_value'], step=1000.0)
        is_second_home = st.checkbox('Is this a second home?', value=settings['is_second_home'])
        
        st.subheader('Mortgage Details')
        deposit_type = st.radio('Deposit Input Type', ['Percentage', 'Fixed Amount'], 
                              index=0 if settings['deposit_type'] == 'Percentage' else 1)
        
        if deposit_type == 'Percentage':
            deposit_percentage = st.number_input('Deposit Percentage (%)', 
                min_value=5.0, max_value=100.0, 
                value=float(settings['deposit_percentage']), 
                step=0.1,
                format="%.1f"
            )
            deposit = property_value * (deposit_percentage / 100)
        else:
            deposit = st.number_input('Deposit Amount (£)', min_value=0.0, value=settings['deposit_amount'], step=1000.0)
        
        loan_amount = property_value - deposit
        mortgage_rate = st.number_input('Mortgage Interest Rate (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(settings['mortgage_rate']), 
            step=0.1,
            format="%.2f"
        ) / 100
        loan_term = st.number_input('Loan Term (years)', 
            min_value=5, max_value=35, 
            value=int(settings['loan_term']), 
            step=1
        )
        
        st.subheader('Additional Costs')
        conveyancing_fees = st.number_input('Conveyancing Fees (£)', min_value=0.0, value=settings['conveyancing_fees'], step=100.0)
        selling_agent_fees = st.number_input('Selling Agent Fees (%)', 
            min_value=0.0, max_value=10.0, 
            value=float(settings['selling_agent_fees']), 
            step=0.1,
            format="%.2f"
        ) / 100
        home_insurance = st.number_input('Annual Home Insurance (£)', min_value=0.0, value=settings['home_insurance'], step=10.0)
        upfront_renovation = st.number_input('Upfront Renovation Cost (£)', min_value=0.0, value=settings['upfront_renovation'], step=100.0)
        upfront_furniture = st.number_input('Upfront Furniture Cost (£)', min_value=0.0, value=settings['upfront_furniture'], step=100.0)
        
        st.subheader('Market Conditions')
        home_appreciation = st.number_input('Annual Home Appreciation Rate (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(settings['home_appreciation']), 
            step=0.1,
            format="%.2f"
        ) / 100
        investment_return = st.number_input('Investment Return Rate (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(settings['investment_return']), 
            step=0.1,
            format="%.2f"
        ) / 100
        
        st.subheader('Rental Income')
        include_rental = st.checkbox('Include Rental Income', value=settings['include_rental'])
        room_rent = None
        room_rent_increase = None
        months_rented = None
        if include_rental:
            room_rent = st.number_input('Monthly Room Rent (£)', min_value=0.0, value=settings['room_rent'], step=10.0)
            room_rent_increase = st.number_input('Annual Room Rent Increase (%)', 
                min_value=0.0, max_value=20.0, 
                value=float(settings['room_rent_increase']), 
                step=0.1,
                format="%.2f"
            ) / 100
            months_rented = st.number_input('Months Rented Per Year', 
                min_value=1, max_value=12, 
                value=int(settings['months_rented']), 
                step=1
            )
        
        st.subheader('Rental Scenario')
        monthly_rent = st.number_input('Monthly Rent Payment (£)', min_value=0.0, value=settings['monthly_rent'], step=10.0)
        rent_increase = st.number_input('Annual Rent Increase (%)', 
            min_value=0.0, max_value=20.0, 
            value=float(settings['rent_increase']), 
            step=0.1,
            format="%.2f"
        ) / 100
        
        st.subheader('Common Parameters')
        utilities = st.number_input('Monthly Utilities (£)', min_value=0.0, value=settings['utilities'], step=10.0)
        sell_after = st.number_input('Sell After (years)', 
            min_value=1, max_value=50, 
            value=int(settings['sell_after']), 
            step=1
        )
        child_years = st.number_input('Years Your Child Will Live In Property', 
            min_value=1, max_value=10, 
            value=int(settings['child_years']), 
            step=1
        )
        
        # Add a reset button
        if st.button('Reset to Defaults'):
            settings = DEFAULT_SETTINGS.copy()
            save_settings(settings)
            st.experimental_rerun()
    
    # Save current settings
    current_settings = {
        'property_value': property_value,
        'is_second_home': is_second_home,
        'deposit_type': deposit_type,
        'deposit_percentage': deposit_percentage if deposit_type == 'Percentage' else settings['deposit_percentage'],
        'deposit_amount': deposit if deposit_type == 'Fixed Amount' else settings['deposit_amount'],
        'mortgage_rate': mortgage_rate * 100,  # Store as percentage
        'loan_term': loan_term,
        'conveyancing_fees': conveyancing_fees,
        'selling_agent_fees': selling_agent_fees * 100,  # Store as percentage
        'home_insurance': home_insurance,
        'upfront_renovation': upfront_renovation,
        'upfront_furniture': upfront_furniture,
        'home_appreciation': home_appreciation * 100,  # Store as percentage
        'investment_return': investment_return * 100,  # Store as percentage
        'include_rental': include_rental,
        'room_rent': room_rent if room_rent is not None else settings['room_rent'],
        'room_rent_increase': room_rent_increase * 100 if room_rent_increase is not None else settings['room_rent_increase'],
        'months_rented': months_rented if months_rented is not None else settings['months_rented'],
        'monthly_rent': monthly_rent,
        'rent_increase': rent_increase * 100,  # Store as percentage
        'utilities': utilities,
        'sell_after': sell_after,
        'child_years': child_years
    }
    save_settings(current_settings)
    
    # Calculate stamp duty
    stamp_duty = calculate_stamp_duty(property_value, is_second_home)
    
    # Create scenario objects
    buy = BuyScenario(
        mortgage_rate=mortgage_rate,
        loan_term=loan_term,
        deposit=deposit,
        conveyancing_fees=conveyancing_fees,
        property_value=property_value,
        stamp_duty=stamp_duty,
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
    
    # Cost Breakdown
    st.subheader('Cost Breakdown')
    col1, col2 = st.columns(2)
    
    with col1:
        st.write('Buy Scenario Initial Costs')
        st.write(f'• Deposit: £{deposit:,.2f}')
        st.write(f'• Stamp Duty: £{stamp_duty:,.2f}')
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
    
    # Balance Sheet Analysis
    st.subheader('Balance Sheet Analysis')
    balance_tab1, balance_tab2 = st.tabs(['Buy Scenario', 'Rent Scenario'])
    
    with balance_tab1:
        buy_df = pd.DataFrame([{
            'Year': d['year'],
            'Property Value': d['property_value'],
            'Mortgage Balance': d['mortgage_balance'],
            'Equity': d['equity'],
            'Net Worth': d['property_value'] - d['mortgage_balance']
        } for d in results['buy_yearly_details']])
        
        # Format all columns except 'Year' with currency
        buy_df_styled = buy_df.style.format({
            'Property Value': '£{:,.2f}',
            'Mortgage Balance': '£{:,.2f}',
            'Equity': '£{:,.2f}',
            'Net Worth': '£{:,.2f}',
            'Year': '{:.0f}'  # Format Year as integer
        })
        st.dataframe(buy_df_styled, hide_index=True)
    
    with balance_tab2:
        rent_df = pd.DataFrame([{
            'Year': d['year'],
            'Bank Balance': d['bank_balance'],
            'Cash Flow': d['cash_flow']
        } for d in results['rent_yearly_details']])
        
        # Format all columns except 'Year' with currency
        rent_df_styled = rent_df.style.format({
            'Bank Balance': '£{:,.2f}',
            'Cash Flow': '£{:,.2f}',
            'Year': '{:.0f}'  # Format Year as integer
        })
        st.dataframe(rent_df_styled, hide_index=True)
    
    # Cash Flow Analysis
    st.subheader('Cash Flow Analysis')
    cashflow_tab1, cashflow_tab2 = st.tabs(['Buy Scenario', 'Rent Scenario'])
    
    with cashflow_tab1:
        buy_cashflow_df = pd.DataFrame([{
            'Year': d['year'],
            'Total Cash Flow': d['cash_flow'],
            **d['components']
        } for d in results['buy_yearly_details']])
        
        # Create format dictionary for all columns
        format_dict = {col: '£{:,.2f}' for col in buy_cashflow_df.columns}
        format_dict['Year'] = '{:.0f}'  # Format Year as integer
        
        buy_cashflow_styled = buy_cashflow_df.style.format(format_dict)
        st.dataframe(buy_cashflow_styled, hide_index=True)
    
    with cashflow_tab2:
        rent_cashflow_df = pd.DataFrame([{
            'Year': d['year'],
            'Total Cash Flow': d['cash_flow'],
            'Rent Paid': d.get('rent_paid', 0),
            'Utilities': d.get('utilities', 0)
        } for d in results['rent_yearly_details']])
        
        # Format all columns except 'Year' with currency
        rent_cashflow_styled = rent_cashflow_df.style.format({
            'Total Cash Flow': '£{:,.2f}',
            'Rent Paid': '£{:,.2f}',
            'Utilities': '£{:,.2f}',
            'Year': '{:.0f}'  # Format Year as integer
        })
        st.dataframe(rent_cashflow_styled, hide_index=True)
    
    # Visualization
    st.subheader('Cash Flow Comparison')
    st.plotly_chart(plot_cash_flows(results))
    
    # Detailed Analysis and Recommendation
    st.subheader('Detailed Analysis')
    recommendation = generate_recommendation(results, buy, rent, common)
    st.write(recommendation)
    
    # Final Position
    st.subheader('Final Position')
    final_col1, final_col2 = st.columns(2)
    with final_col1:
        st.metric('Buy Scenario Net Worth', f'£{final_buy_position:,.2f}')
    with final_col2:
        st.metric('Rent Scenario Net Worth', f'£{final_rent_position:,.2f}')
    st.write(f'Difference: £{abs(final_buy_position - final_rent_position):,.2f} in favor of {"buying" if final_buy_position > final_rent_position else "renting"}')

if __name__ == '__main__':
    main() 