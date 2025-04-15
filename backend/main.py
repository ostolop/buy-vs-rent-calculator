from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import numpy as np
import numpy_financial as npf
import pandas as pd
from datetime import datetime

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BuyScenario(BaseModel):
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
    loan_amount: float  # This will be computed from property_value - deposit
    is_second_home: bool = False
    cgt_rate: float = 0.28  # Default CGT rate for residential property

class RentScenario(BaseModel):
    rent_per_month: float
    rent_annual_increase: float

class CommonParams(BaseModel):
    utilities_per_month: float
    sell_after_years: int
    daughter_living_years: int

class AnalysisRequest(BaseModel):
    buy: BuyScenario
    rent: RentScenario
    common: CommonParams

def calculate_mortgage_payment(principal, annual_rate, years):
    monthly_rate = annual_rate / 12
    num_payments = years * 12
    return principal * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)

def calculate_stamp_duty(property_value: float, is_second_home: bool = False) -> float:
    if is_second_home:
        # Second home rates (2025)
        bands = [
            (0, 125000, 0.05),
            (125001, 250000, 0.07),
            (250001, float('inf'), 0.10)
        ]
    else:
        # Standard rates (2025)
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

def calculate_cash_flows(request: AnalysisRequest):
    # Initialize arrays for cash flows
    years = np.arange(0, request.common.sell_after_years + 1)  # Include year 0 for initial costs
    
    # Calculate stamp duty
    stamp_duty = calculate_stamp_duty(request.buy.property_value, request.buy.is_second_home)
    request.buy.stamp_duty = stamp_duty
    
    # Buy scenario calculations
    total_property_cost = request.buy.property_value + request.buy.conveyancing_fees + request.buy.stamp_duty
    monthly_mortgage = calculate_mortgage_payment(
        request.buy.loan_amount,
        request.buy.mortgage_rate,
        request.buy.loan_term
    )
    
    # Initialize arrays for buy scenario
    buy_cash_flow = np.zeros_like(years, dtype=float)
    property_value = np.zeros_like(years, dtype=float)
    mortgage_balance = np.zeros_like(years, dtype=float)
    accumulated_equity = np.zeros_like(years, dtype=float)
    buy_balance_sheet = []
    buy_bank_balance = np.zeros_like(years, dtype=float)  # Track bank account balance
    
    # Initialize detailed breakdown arrays
    buy_breakdown = []
    rent_breakdown = []
    
    # Track investment opportunity cost for deposit
    deposit_investment_balance = request.buy.deposit
    
    # Initial costs (Year 0)
    initial_costs = {
        "deposit": -request.buy.deposit,
        "conveyancing_fees": -request.buy.conveyancing_fees,
        "stamp_duty": -request.buy.stamp_duty,
        "upfront_renovation": -request.buy.upfront_renovation_cost,
        "upfront_furniture": -request.buy.upfront_furniture_cost
    }
    buy_cash_flow[0] = sum(initial_costs.values())
    buy_bank_balance[0] = -sum(initial_costs.values())  # Initial bank balance is negative of initial costs
    buy_breakdown.append({
        "year": 0,
        "total": buy_cash_flow[0],
        "components": initial_costs
    })
    
    # Initial balance sheet (Year 0)
    buy_balance_sheet.append({
        "year": 0,
        "assets": {
            "property_value": request.buy.property_value,
            "equity": request.buy.deposit,
            "total_assets": request.buy.property_value
        },
        "liabilities": {
            "mortgage_balance": request.buy.loan_amount,
            "total_liabilities": request.buy.loan_amount
        },
        "net_worth": request.buy.deposit
    })
    
    property_value[0] = request.buy.property_value
    mortgage_balance[0] = request.buy.loan_amount
    accumulated_equity[0] = request.buy.deposit
    
    # Calculate yearly cash flows starting from Year 1
    for i in range(1, len(years)):
        # Property appreciation
        property_value[i] = property_value[i-1] * (1 + request.buy.home_appreciation_rate)
        
        # Initialize components for this year
        buy_components = {}
        
        # Calculate opportunity cost of deposit (investment returns that could have been earned)
        deposit_investment_return = deposit_investment_balance * request.buy.investment_return_rate
        deposit_investment_balance += deposit_investment_return
        buy_components["deposit_opportunity_cost"] = -deposit_investment_return
        buy_cash_flow[i] -= deposit_investment_return
        
        # Mortgage payments
        yearly_mortgage = monthly_mortgage * 12
        interest_payment = mortgage_balance[i-1] * request.buy.mortgage_rate
        principal_payment = yearly_mortgage - interest_payment
        mortgage_balance[i] = mortgage_balance[i-1] - principal_payment
        accumulated_equity[i] = accumulated_equity[i-1] + principal_payment
        
        buy_components["mortgage_payments"] = -yearly_mortgage
        buy_cash_flow[i] -= yearly_mortgage
        
        # Home insurance
        buy_components["home_insurance"] = -request.buy.home_insurance
        buy_cash_flow[i] -= request.buy.home_insurance
        
        # Utilities
        buy_components["utilities"] = -request.common.utilities_per_month * 12
        buy_cash_flow[i] -= request.common.utilities_per_month * 12
        
        # Room rental income if applicable
        if request.buy.room_rent is not None and request.buy.room_rent_increase is not None and request.buy.months_rented_per_year is not None and i <= request.common.daughter_living_years:
            room_rent = request.buy.room_rent * (1 + request.buy.room_rent_increase) ** (i-1)
            room_rent_income = room_rent * request.buy.months_rented_per_year
            buy_components["room_rent_income"] = room_rent_income
            buy_cash_flow[i] += room_rent_income
        
        # Full house rental if daughter moved out
        if i > request.common.daughter_living_years and i <= request.common.sell_after_years:
            if request.buy.room_rent is not None and request.buy.room_rent_increase is not None:
                room_rent = request.buy.room_rent * (1 + request.buy.room_rent_increase) ** (i-1)
                full_rent_income = room_rent * 12 * 2
                buy_components["full_house_rent_income"] = full_rent_income
                buy_cash_flow[i] += full_rent_income
        
        # Update bank balance
        buy_bank_balance[i] = buy_bank_balance[i-1] + buy_cash_flow[i]
        
        buy_breakdown.append({
            "year": i,
            "total": buy_cash_flow[i],
            "components": buy_components,
            "bank_balance": buy_bank_balance[i]
        })
        
        # Calculate balance sheet for this year
        buy_balance_sheet.append({
            "year": i,
            "assets": {
                "property_value": property_value[i],
                "equity": accumulated_equity[i],
                "total_assets": property_value[i]
            },
            "liabilities": {
                "mortgage_balance": mortgage_balance[i],
                "total_liabilities": mortgage_balance[i]
            },
            "net_worth": property_value[i] - mortgage_balance[i]
        })
    
    # Selling the property
    if request.common.sell_after_years <= request.common.sell_after_years:
        selling_year = request.common.sell_after_years
        selling_price = property_value[selling_year]
        agent_fees = selling_price * request.buy.selling_agent_fees_percent
        remaining_mortgage = mortgage_balance[selling_year]
        
        # Calculate capital gains tax
        original_cost = request.buy.property_value + request.buy.conveyancing_fees + request.buy.stamp_duty
        
        # Calculate total mortgage interest paid over the years
        total_mortgage_interest = 0
        for i in range(request.common.sell_after_years + 1):  # Include the selling year
            yearly_mortgage = monthly_mortgage * 12
            interest_payment = mortgage_balance[i] * request.buy.mortgage_rate
            total_mortgage_interest += interest_payment
        
        # Calculate total rental income
        total_rental_income = 0
        for i in range(request.common.sell_after_years + 1):  # Include the selling year
            if i < request.common.daughter_living_years:
                if request.buy.room_rent is not None and request.buy.room_rent_increase is not None and request.buy.months_rented_per_year is not None:
                    room_rent = request.buy.room_rent * (1 + request.buy.room_rent_increase) ** i
                    total_rental_income += room_rent * request.buy.months_rented_per_year
            else:
                if request.buy.room_rent is not None and request.buy.room_rent_increase is not None:
                    room_rent = request.buy.room_rent * (1 + request.buy.room_rent_increase) ** i
                    total_rental_income += room_rent * 12 * 2  # Full house rental
        
        # Calculate mortgage interest deduction (20% of total mortgage interest)
        mortgage_interest_deduction = total_mortgage_interest * 0.20
        
        # Calculate taxable gain after mortgage interest deduction
        capital_gain = selling_price - original_cost
        taxable_gain = max(0, capital_gain - mortgage_interest_deduction)
        cgt = taxable_gain * request.buy.cgt_rate  # CGT only applies to gains
        
        selling_components = {
            "property_sale": selling_price,
            "agent_fees": -agent_fees,
            "mortgage_repayment": -remaining_mortgage,
            "capital_gains_tax": -cgt,
            "mortgage_interest_deduction": mortgage_interest_deduction
        }
        
        sale_proceeds = selling_price - agent_fees - remaining_mortgage - cgt
        buy_cash_flow[selling_year] += sale_proceeds
        buy_bank_balance[selling_year] = buy_bank_balance[selling_year-1] + sale_proceeds if selling_year > 0 else sale_proceeds
        
        buy_breakdown[selling_year]["components"].update(selling_components)
        buy_breakdown[selling_year]["total"] = buy_cash_flow[selling_year]
        
        # Update final balance sheet after sale
        buy_balance_sheet[selling_year]["assets"]["property_value"] = 0
        buy_balance_sheet[selling_year]["assets"]["cash"] = sale_proceeds
        buy_balance_sheet[selling_year]["assets"]["equity"] = accumulated_equity[selling_year]
        buy_balance_sheet[selling_year]["assets"]["total_assets"] = sale_proceeds
        buy_balance_sheet[selling_year]["liabilities"]["mortgage_balance"] = 0
        buy_balance_sheet[selling_year]["liabilities"]["total_liabilities"] = 0
        buy_balance_sheet[selling_year]["net_worth"] = sale_proceeds
    
    # Rent scenario calculations
    rent_cash_flow = np.zeros_like(years, dtype=float)
    investment_balance = request.buy.deposit
    total_rent_paid = 0
    rent_balance_sheet = []
    rent_bank_balance = np.zeros_like(years, dtype=float)  # Track bank account balance
    
    # Initial bank balance for rent scenario starts with the deposit
    rent_bank_balance[0] = request.buy.deposit  # Just the deposit in Year 0
    
    # Add initial breakdown for Year 0
    rent_breakdown.append({
        "year": 0,
        "total": 0,
        "components": {
            "initial_deposit": request.buy.deposit
        },
        "investment_balance": request.buy.deposit,
        "bank_balance": request.buy.deposit
    })
    
    # Initial balance sheet for Year 0
    rent_balance_sheet.append({
        "year": 0,
        "assets": {
            "investment_balance": request.buy.deposit,
            "total_assets": request.buy.deposit
        },
        "liabilities": {
            "total_liabilities": 0
        },
        "net_worth": request.buy.deposit
    })
    
    # Calculate rent scenario starting from Year 1
    for i in range(1, len(years)):
        rent_components = {}
        
        # Investment returns on entire portfolio
        investment_return = investment_balance * request.buy.investment_return_rate
        rent_components["investment_returns"] = investment_return
        rent_cash_flow[i] += investment_return
        investment_balance += investment_return
        
        # Only include rent for years when daughter is living there
        if i <= request.common.daughter_living_years:  # Changed < to <= to include the final year
            yearly_rent = request.rent.rent_per_month * 12 * (1 + request.rent.rent_annual_increase) ** (i-1)
            rent_components["rent_payments"] = -yearly_rent
            rent_cash_flow[i] -= yearly_rent
            total_rent_paid += yearly_rent
            # Update bank balance: previous balance + investment returns - rent
            rent_bank_balance[i] = rent_bank_balance[i-1] + investment_return - yearly_rent
        else:
            rent_components["rent_payments"] = 0
            rent_cash_flow[i] += 0
            # Update bank balance: previous balance + investment returns
            rent_bank_balance[i] = rent_bank_balance[i-1] + investment_return
        
        rent_breakdown.append({
            "year": i,
            "total": rent_cash_flow[i],
            "components": rent_components,
            "investment_balance": investment_balance,
            "bank_balance": rent_bank_balance[i]
        })
        
        # Calculate balance sheet for this year
        rent_balance_sheet.append({
            "year": i,
            "assets": {
                "investment_balance": investment_balance,
                "total_assets": investment_balance
            },
            "liabilities": {
                "total_liabilities": 0
            },
            "net_worth": investment_balance - total_rent_paid
        })
    
    return {
        "years": years.tolist(),
        "buy_cash_flow": buy_cash_flow.tolist(),
        "rent_cash_flow": rent_cash_flow.tolist(),
        "property_value": property_value.tolist(),
        "mortgage_balance": mortgage_balance.tolist(),
        "buy_breakdown": buy_breakdown,
        "rent_breakdown": rent_breakdown,
        "buy_balance_sheet": buy_balance_sheet,
        "rent_balance_sheet": rent_balance_sheet,
        "buy_bank_balance": buy_bank_balance.tolist(),  # Add bank balances to response
        "rent_bank_balance": rent_bank_balance.tolist()
    }

def generate_recommendation_explanation(buy_npv: float, rent_npv: float, results: dict, request: AnalysisRequest) -> str:
    total_buy_cost = sum(results["buy_cash_flow"])
    total_rent_cost = sum(results["rent_cash_flow"])
    property_appreciation = results["property_value"][-1] - request.buy.property_value
    total_investment_returns = results["rent_breakdown"][-1]["investment_balance"] - request.buy.deposit
    
    # Calculate total costs and gains separately
    buy_costs = sum(min(0, x) for x in results["buy_cash_flow"])
    buy_gains = sum(max(0, x) for x in results["buy_cash_flow"])
    rent_costs = sum(min(0, x) for x in results["rent_cash_flow"])
    rent_gains = sum(max(0, x) for x in results["rent_cash_flow"])
    
    # Calculate total opportunity cost of deposit
    total_deposit_opportunity_cost = sum(
        year["components"].get("deposit_opportunity_cost", 0)
        for year in results["buy_breakdown"]
    )
    
    # Calculate capital gains tax
    selling_year = request.common.sell_after_years - 1
    cgt = results["buy_breakdown"][selling_year]["components"].get("capital_gains_tax", 0)
    
    explanation = []
    
    if buy_npv > rent_npv:
        explanation.append("The Buy scenario is recommended because:")
        explanation.append(f"1. The Net Present Value (NPV) of buying (£{buy_npv:,.2f}) is higher than renting (£{rent_npv:,.2f})")
        explanation.append(f"2. The property is expected to appreciate by £{property_appreciation:,.2f} over the analysis period")
        explanation.append(f"3. Financial Summary:")
        explanation.append(f"   - Total costs: £{abs(buy_costs):,.2f}")
        explanation.append(f"   - Total gains: £{buy_gains:,.2f}")
        explanation.append(f"   - Net result: £{total_buy_cost:,.2f}")
        explanation.append(f"   - Opportunity cost of deposit: £{abs(total_deposit_opportunity_cost):,.2f}")
        explanation.append(f"   - Capital gains tax on sale: £{abs(cgt):,.2f}")
        
        # Add specific factors that made buying better
        if request.buy.room_rent is not None:
            total_room_rent = sum(year["components"].get("room_rent_income", 0) for year in results["buy_breakdown"])
            explanation.append(f"4. Room rental income contributes £{total_room_rent:,.2f} to offset costs")
        
        if request.common.sell_after_years < request.common.sell_after_years:
            selling_profit = results["property_value"][request.common.sell_after_years - 1] - request.buy.property_value
            explanation.append(f"5. Selling the property after {request.common.sell_after_years} years would generate a profit of £{selling_profit:,.2f} (before tax)")
    else:
        explanation.append("The Rent scenario is recommended because:")
        explanation.append(f"1. The Net Present Value (NPV) of renting (£{rent_npv:,.2f}) is higher than buying (£{buy_npv:,.2f})")
        explanation.append(f"2. The deposit (£{request.buy.deposit:,.2f}) would generate £{total_investment_returns:,.2f} in investment returns")
        explanation.append(f"3. Financial Summary:")
        explanation.append(f"   - Total costs: £{abs(rent_costs):,.2f}")
        explanation.append(f"   - Total gains: £{rent_gains:,.2f}")
        explanation.append(f"   - Net result: £{total_rent_cost:,.2f}")
        explanation.append(f"   - Investment returns on deposit: £{total_investment_returns:,.2f}")
        
        # Add specific factors that made renting better
        if request.buy.stamp_duty > 0:
            explanation.append(f"4. Avoiding stamp duty costs of £{request.buy.stamp_duty:,.2f}")
        
        if request.buy.conveyancing_fees > 0:
            explanation.append(f"5. Avoiding conveyancing fees of £{request.buy.conveyancing_fees:,.2f}")
        
        explanation.append(f"6. The opportunity cost of tying up the deposit in property (£{abs(total_deposit_opportunity_cost):,.2f}) makes renting more attractive")
        explanation.append(f"7. Avoiding capital gains tax of £{abs(cgt):,.2f} that would be due on property sale")
    
    return "\n".join(explanation)

@app.post("/analyze")
async def analyze_scenario(request: AnalysisRequest):
    try:
        # Calculate monthly mortgage payment first
        monthly_mortgage = calculate_mortgage_payment(
            request.buy.loan_amount,
            request.buy.mortgage_rate,
            request.buy.loan_term
        )
        
        results = calculate_cash_flows(request)
        
        # Calculate NPV for both scenarios
        buy_npv = npf.npv(request.buy.investment_return_rate, results["buy_cash_flow"])
        rent_npv = npf.npv(request.buy.investment_return_rate, results["rent_cash_flow"])
        
        # Calculate total costs
        total_buy_cost = sum(results["buy_cash_flow"])
        total_rent_cost = sum(results["rent_cash_flow"])
        
        recommendation = "Buy" if buy_npv > rent_npv else "Rent"
        explanation = generate_recommendation_explanation(buy_npv, rent_npv, results, request)
        
        return {
            "cash_flows": results,
            "npv": {
                "buy": buy_npv,
                "rent": rent_npv
            },
            "total_costs": {
                "buy": total_buy_cost,
                "rent": total_rent_cost
            },
            "cost_breakdown": {
                "buy": {
                    "initial_costs": {
                        "deposit": request.buy.deposit,
                        "conveyancing_fees": request.buy.conveyancing_fees,
                        "stamp_duty": request.buy.stamp_duty,
                        "upfront_renovation": request.buy.upfront_renovation_cost,
                        "upfront_furniture": request.buy.upfront_furniture_cost
                    },
                    "ongoing_costs": {
                        "mortgage_payments": -monthly_mortgage * 12 * request.common.sell_after_years,
                        "home_insurance": request.buy.home_insurance * request.common.sell_after_years,
                        "utilities": request.common.utilities_per_month * 12 * request.common.sell_after_years
                    },
                    "selling_costs": {
                        "agent_fees": results["property_value"][request.common.sell_after_years - 1] * request.buy.selling_agent_fees_percent if request.common.sell_after_years <= request.common.sell_after_years else 0
                    }
                },
                "rent": {
                    "rent_payments": sum([-request.rent.rent_per_month * 12 * (1 + request.rent.rent_annual_increase) ** i for i in range(request.common.daughter_living_years)]),
                    "utilities": request.common.utilities_per_month * 12 * request.common.sell_after_years
                }
            },
            "recommendation": recommendation,
            "explanation": explanation,
            "analysis_years": request.common.sell_after_years
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Student Accommodation Calculator API"} 