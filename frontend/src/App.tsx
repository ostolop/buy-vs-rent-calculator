import React, { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Typography,
  TextField,
  Button,
  Grid,
  Box,
  Tabs,
  Tab,
  FormControlLabel,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Divider,
} from '@mui/material';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

interface BuyScenario {
  mortgage_rate: number;
  loan_term: number;
  deposit: number;
  conveyancing_fees: number;
  property_value: number;
  stamp_duty: number;
  selling_agent_fees_percent: number;
  home_appreciation_rate: number;
  investment_return_rate: number;
  upfront_renovation_cost: number;
  upfront_furniture_cost: number;
  home_insurance: number;
  room_rent?: number;
  room_rent_increase?: number;
  months_rented_per_year?: number;
  is_second_home: boolean;
}

interface RentScenario {
  rent_per_month: number;
  rent_annual_increase: number;
}

interface CommonParams {
  utilities_per_month: number;
  sell_after_years: number;
  daughter_living_years: number;
}

interface AnalysisResult {
  cash_flows: {
    years: number[];
    buy_cash_flow: number[];
    rent_cash_flow: number[];
    property_value: number[];
    mortgage_balance: number[];
    buy_breakdown: Array<{
      year: number;
      total: number;
      components: {
        [key: string]: number;
      };
    }>;
    rent_breakdown: Array<{
      year: number;
      total: number;
      components: {
        [key: string]: number;
      };
      investment_balance: number;
    }>;
    buy_balance_sheet: Array<{
      year: number;
      assets: {
        property_value: number;
        cash?: number;
        total_assets: number;
      };
      liabilities: {
        mortgage_balance: number;
        total_liabilities: number;
      };
      net_worth: number;
    }>;
    rent_balance_sheet: Array<{
      year: number;
      assets: {
        investment_balance: number;
        total_assets: number;
      };
      liabilities: {
        total_liabilities: number;
      };
      net_worth: number;
    }>;
    buy_bank_balance: number[];
    rent_bank_balance: number[];
  };
  npv: {
    buy: number;
    rent: number;
  };
  total_costs: {
    buy: number;
    rent: number;
  };
  cost_breakdown: {
    buy: {
      initial_costs: {
        deposit: number;
        conveyancing_fees: number;
        stamp_duty: number;
        upfront_renovation: number;
        upfront_furniture: number;
      };
      ongoing_costs: {
        mortgage_payments: number;
        home_insurance: number;
        utilities: number;
      };
      selling_costs: {
        agent_fees: number;
      };
    };
    rent: {
      rent_payments: number;
      utilities: number;
    };
  };
  recommendation: string;
  explanation: string;
  sell_after_years: number;
}

const App: React.FC = () => {
  // Load initial state from localStorage or use defaults
  const loadFromStorage = <T,>(key: string, defaultValue: T): T => {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : defaultValue;
  };

  const saveToStorage = <T,>(key: string, value: T) => {
    localStorage.setItem(key, JSON.stringify(value));
  };

  const defaultBuyScenario: BuyScenario = {
    mortgage_rate: 0.05,
    loan_term: 25,
    deposit: 50000,
    conveyancing_fees: 2000,
    property_value: 250000,
    stamp_duty: 0,
    selling_agent_fees_percent: 0.015,
    home_appreciation_rate: 0.03,
    investment_return_rate: 0.07,
    upfront_renovation_cost: 10000,
    upfront_furniture_cost: 5000,
    home_insurance: 500,
    is_second_home: false,
  };

  const defaultRentScenario: RentScenario = {
    rent_per_month: 800,
    rent_annual_increase: 0.03,
  };

  const defaultCommonParams: CommonParams = {
    utilities_per_month: 200,
    sell_after_years: 5,
    daughter_living_years: 3,
  };

  const [buyScenario, setBuyScenario] = useState<BuyScenario>(
    loadFromStorage('buyScenario', defaultBuyScenario)
  );
  const [rentScenario, setRentScenario] = useState<RentScenario>(
    loadFromStorage('rentScenario', defaultRentScenario)
  );
  const [commonParams, setCommonParams] = useState<CommonParams>(
    loadFromStorage('commonParams', defaultCommonParams)
  );
  const [includeRoomRent, setIncludeRoomRent] = useState<boolean>(
    loadFromStorage('includeRoomRent', false)
  );
  const [activeTab, setActiveTab] = useState<number>(
    loadFromStorage('activeTab', 0)
  );

  // Save to localStorage whenever state changes
  useEffect(() => {
    saveToStorage('buyScenario', buyScenario);
  }, [buyScenario]);

  useEffect(() => {
    saveToStorage('rentScenario', rentScenario);
  }, [rentScenario]);

  useEffect(() => {
    saveToStorage('commonParams', commonParams);
  }, [commonParams]);

  useEffect(() => {
    saveToStorage('includeRoomRent', includeRoomRent);
  }, [includeRoomRent]);

  useEffect(() => {
    saveToStorage('activeTab', activeTab);
  }, [activeTab]);

  const [results, setResults] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleBuyScenarioChange = (field: keyof BuyScenario) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = parseFloat(event.target.value);
    setBuyScenario({
      ...buyScenario,
      [field]: field === 'mortgage_rate' || 
               field === 'selling_agent_fees_percent' || 
               field === 'home_appreciation_rate' || 
               field === 'investment_return_rate' || 
               field === 'room_rent_increase' ? value / 100 : value,
    });
  };

  const handleRentScenarioChange = (field: keyof RentScenario) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = parseFloat(event.target.value);
    setRentScenario({
      ...rentScenario,
      [field]: field === 'rent_annual_increase' ? value / 100 : value,
    });
  };

  const handleCommonParamsChange = (field: keyof CommonParams) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    setCommonParams({
      ...commonParams,
      [field]: parseFloat(event.target.value),
    });
  };

  const handleAnalyze = async () => {
    try {
      setError(null);
      // Calculate loan amount based on property value and deposit
      const loan_amount = buyScenario.property_value - buyScenario.deposit;
      
      // Prepare buy scenario data based on includeRoomRent toggle
      const buyScenarioData = {
        ...buyScenario,
        loan_amount,
        room_rent: includeRoomRent ? buyScenario.room_rent : null,
        room_rent_increase: includeRoomRent ? buyScenario.room_rent_increase : null,
        months_rented_per_year: includeRoomRent ? buyScenario.months_rented_per_year : null,
      };
      
      const response = await fetch('http://localhost:8000/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          buy: buyScenarioData,
          rent: rentScenario,
          common: commonParams,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'An error occurred while analyzing the scenario');
      }

      const data = await response.json();
      setResults(data);
    } catch (error) {
      console.error('Error analyzing scenario:', error);
      setError(error instanceof Error ? error.message : 'An unexpected error occurred');
      setResults(null);
    }
  };

  const chartData = results?.cash_flows ? {
    labels: results.cash_flows.years.map((year) => `Year ${year}`),
    datasets: [
      {
        label: 'Buy Scenario',
        data: results.cash_flows.buy_cash_flow,
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
      {
        label: 'Rent Scenario',
        data: results.cash_flows.rent_cash_flow,
        borderColor: 'rgb(255, 99, 132)',
        tension: 0.1,
      },
    ],
  } : {
    labels: [],
    datasets: [
      {
        label: 'Buy Scenario',
        data: [],
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
      {
        label: 'Rent Scenario',
        data: [],
        borderColor: 'rgb(255, 99, 132)',
        tension: 0.1,
      },
    ],
  };

  const balanceChartData = results?.cash_flows ? {
    labels: results.cash_flows.years.map((year) => `Year ${year}`),
    datasets: [
      {
        label: 'Buy Scenario Net Worth',
        data: results.cash_flows.buy_balance_sheet.map(sheet => sheet.net_worth),
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
      {
        label: 'Rent Scenario Net Worth',
        data: results.cash_flows.rent_balance_sheet.map(sheet => sheet.net_worth),
        borderColor: 'rgb(255, 99, 132)',
        tension: 0.1,
      },
    ],
  } : {
    labels: [],
    datasets: [
      {
        label: 'Buy Scenario Net Worth',
        data: [],
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
      {
        label: 'Rent Scenario Net Worth',
        data: [],
        borderColor: 'rgb(255, 99, 132)',
        tension: 0.1,
      },
    ],
  };

  const bankBalanceChartData = results?.cash_flows ? {
    labels: results.cash_flows.years.map((year) => `Year ${year}`),
    datasets: [
      {
        label: 'Buy Scenario Bank Balance',
        data: results.cash_flows.buy_bank_balance,
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
      {
        label: 'Rent Scenario Bank Balance',
        data: results.cash_flows.rent_bank_balance,
        borderColor: 'rgb(255, 99, 132)',
        tension: 0.1,
      },
    ],
  } : {
    labels: [],
    datasets: [
      {
        label: 'Buy Scenario Bank Balance',
        data: [],
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1,
      },
      {
        label: 'Rent Scenario Bank Balance',
        data: [],
        borderColor: 'rgb(255, 99, 132)',
        tension: 0.1,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: 'Cash Flow Comparison',
      },
    },
    scales: {
      y: {
        beginAtZero: false,
        title: {
          display: true,
          text: 'Cash Flow (£)',
        },
      },
      x: {
        title: {
          display: true,
          text: 'Year',
        },
      },
    },
  };

  const balanceChartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: 'Net Worth Comparison',
      },
    },
    scales: {
      y: {
        beginAtZero: false,
        title: {
          display: true,
          text: 'Net Worth (£)',
        },
      },
      x: {
        title: {
          display: true,
          text: 'Year',
        },
      },
    },
  };

  const bankBalanceChartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: 'Bank Account Balance Comparison',
      },
    },
    scales: {
      y: {
        beginAtZero: false,
        title: {
          display: true,
          text: 'Bank Balance (£)',
        },
      },
      x: {
        title: {
          display: true,
          text: 'Year',
        },
      },
    },
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Student Accommodation Calculator
        </Typography>

        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Input Parameters
          </Typography>
          <Grid container spacing={2}>
            {/* Buy Scenario Section */}
            <Grid item xs={12}>
              <Typography variant="subtitle1" gutterBottom>
                Buy Scenario
              </Typography>
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={buyScenario.is_second_home}
                    onChange={(e) => {
                      setBuyScenario({
                        ...buyScenario,
                        is_second_home: e.target.checked,
                      });
                    }}
                  />
                }
                label="Second Home (Higher Stamp Duty)"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Mortgage Rate (%)"
                type="number"
                value={buyScenario.mortgage_rate * 100}
                onChange={handleBuyScenarioChange('mortgage_rate')}
                InputProps={{ inputProps: { step: 0.1 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Loan Term (years)"
                type="number"
                value={buyScenario.loan_term}
                onChange={handleBuyScenarioChange('loan_term')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Deposit (£)"
                type="number"
                value={buyScenario.deposit}
                onChange={handleBuyScenarioChange('deposit')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Property Value (£)"
                type="number"
                value={buyScenario.property_value}
                onChange={handleBuyScenarioChange('property_value')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Conveyancing Fees (£)"
                type="number"
                value={buyScenario.conveyancing_fees}
                onChange={handleBuyScenarioChange('conveyancing_fees')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Selling Agent Fees (%)"
                type="number"
                value={buyScenario.selling_agent_fees_percent * 100}
                onChange={handleBuyScenarioChange('selling_agent_fees_percent')}
                InputProps={{ inputProps: { step: 0.1 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Home Appreciation Rate (%)"
                type="number"
                value={buyScenario.home_appreciation_rate * 100}
                onChange={handleBuyScenarioChange('home_appreciation_rate')}
                InputProps={{ inputProps: { step: 0.1 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Investment Return Rate (%)"
                type="number"
                value={buyScenario.investment_return_rate * 100}
                onChange={handleBuyScenarioChange('investment_return_rate')}
                InputProps={{ inputProps: { step: 0.1 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Upfront Renovation Cost (£)"
                type="number"
                value={buyScenario.upfront_renovation_cost}
                onChange={handleBuyScenarioChange('upfront_renovation_cost')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Upfront Furniture Cost (£)"
                type="number"
                value={buyScenario.upfront_furniture_cost}
                onChange={handleBuyScenarioChange('upfront_furniture_cost')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Home Insurance (£/year)"
                type="number"
                value={buyScenario.home_insurance}
                onChange={handleBuyScenarioChange('home_insurance')}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={includeRoomRent}
                    onChange={(e) => setIncludeRoomRent(e.target.checked)}
                  />
                }
                label="Include Room Rental Income"
              />
            </Grid>
            {includeRoomRent && (
              <>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Room Rent (£/month)"
                    type="number"
                    value={buyScenario.room_rent || 0}
                    onChange={handleBuyScenarioChange('room_rent')}
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Room Rent Annual Increase (%)"
                    type="number"
                    value={(buyScenario.room_rent_increase || 0) * 100}
                    onChange={handleBuyScenarioChange('room_rent_increase')}
                    InputProps={{ inputProps: { step: 0.1 } }}
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Months Rented Per Year"
                    type="number"
                    value={buyScenario.months_rented_per_year || 0}
                    onChange={handleBuyScenarioChange('months_rented_per_year')}
                  />
                </Grid>
              </>
            )}
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" sx={{ mt: 2 }}>
                Stamp Duty: £{results?.cost_breakdown?.buy?.initial_costs?.stamp_duty?.toFixed(2) || 'Calculating...'}
              </Typography>
            </Grid>

            {/* Rent Scenario Section */}
            <Grid item xs={12}>
              <Typography variant="subtitle1" sx={{ mt: 2 }} gutterBottom>
                Rent Scenario
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Rent Per Month (£)"
                type="number"
                value={rentScenario.rent_per_month}
                onChange={handleRentScenarioChange('rent_per_month')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Rent Annual Increase (%)"
                type="number"
                value={rentScenario.rent_annual_increase * 100}
                onChange={handleRentScenarioChange('rent_annual_increase')}
                InputProps={{ inputProps: { step: 0.1 } }}
              />
            </Grid>

            {/* Common Parameters Section */}
            <Grid item xs={12}>
              <Typography variant="subtitle1" sx={{ mt: 2 }} gutterBottom>
                Common Parameters
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Utilities Per Month (£)"
                type="number"
                value={commonParams.utilities_per_month}
                onChange={handleCommonParamsChange('utilities_per_month')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Sell After Years"
                type="number"
                value={commonParams.sell_after_years}
                onChange={handleCommonParamsChange('sell_after_years')}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Daughter Living Years"
                type="number"
                value={commonParams.daughter_living_years}
                onChange={handleCommonParamsChange('daughter_living_years')}
              />
            </Grid>
          </Grid>
        </Paper>

        <Button
          variant="contained"
          color="primary"
          onClick={handleAnalyze}
          sx={{ mb: 3 }}
        >
          Analyze Scenarios
        </Button>

        {error && (
          <Paper sx={{ p: 2, mb: 3, bgcolor: 'error.light' }}>
            <Typography color="error">{error}</Typography>
          </Paper>
        )}

        {results && (
          <Paper sx={{ p: 3 }}>
            <Typography variant="h5" gutterBottom>
              Analysis Results
            </Typography>
            <Typography variant="h6" color={results?.recommendation === 'Buy' ? 'success.main' : 'error.main'}>
              Recommendation: {results?.recommendation || 'No recommendation available'}
            </Typography>
            
            <Paper sx={{ p: 2, mt: 2, mb: 3, bgcolor: results?.recommendation === 'Buy' ? 'success.light' : 'error.light' }}>
              <Typography variant="body1" style={{ whiteSpace: 'pre-line' }}>
                {results?.explanation}
              </Typography>
            </Paper>
            
            <Grid container spacing={2} sx={{ mt: 2 }}>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle1">
                  Buy Scenario NPV: £{results?.npv?.buy?.toFixed(2) || 'N/A'}
                </Typography>
                <Typography variant="subtitle1">
                  Total Buy Cost: £{results?.total_costs?.buy?.toFixed(2) || 'N/A'}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle1">
                  Rent Scenario NPV: £{results?.npv?.rent?.toFixed(2) || 'N/A'}
                </Typography>
                <Typography variant="subtitle1">
                  Total Rent Cost: £{results?.total_costs?.rent?.toFixed(2) || 'N/A'}
                </Typography>
              </Grid>
            </Grid>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Cash Flow and Net Worth Comparison
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2, mb: 3 }}>
                    <Line data={chartData} options={chartOptions} />
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2, mb: 3 }}>
                    <Line data={balanceChartData} options={balanceChartOptions} />
                  </Paper>
                </Grid>
              </Grid>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Financial Position Comparison
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2, mb: 3 }}>
                    <Line data={balanceChartData} options={balanceChartOptions} />
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2, mb: 3 }}>
                    <Line data={bankBalanceChartData} options={bankBalanceChartOptions} />
                  </Paper>
                </Grid>
              </Grid>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Bank Account Balance Details
              </Typography>
              <TableContainer component={Paper} sx={{ mt: 2 }}>
                <Table size="small" aria-label="bank balance table">
                  <TableHead>
                    <TableRow>
                      <TableCell>Year</TableCell>
                      <TableCell align="right">Buy Scenario Bank Balance (£)</TableCell>
                      <TableCell align="right">Rent Scenario Bank Balance (£)</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {results?.cash_flows?.years.map((year, index) => (
                      <TableRow key={year}>
                        <TableCell component="th" scope="row">
                          {year}
                        </TableCell>
                        <TableCell align="right">
                          {results.cash_flows.buy_bank_balance[index].toFixed(2)}
                        </TableCell>
                        <TableCell align="right">
                          {results.cash_flows.rent_bank_balance[index].toFixed(2)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Detailed Cost Breakdown
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle1" gutterBottom>
                      Buy Scenario Costs
                    </Typography>
                    <Typography variant="subtitle2" gutterBottom>
                      Initial Costs
                    </Typography>
                    <Typography>Deposit: £{results?.cost_breakdown?.buy?.initial_costs?.deposit?.toFixed(2)}</Typography>
                    <Typography>Conveyancing Fees: £{results?.cost_breakdown?.buy?.initial_costs?.conveyancing_fees?.toFixed(2)}</Typography>
                    <Typography>Stamp Duty: £{results?.cost_breakdown?.buy?.initial_costs?.stamp_duty?.toFixed(2)}</Typography>
                    <Typography>Upfront Renovation: £{results?.cost_breakdown?.buy?.initial_costs?.upfront_renovation?.toFixed(2)}</Typography>
                    <Typography>Upfront Furniture: £{results?.cost_breakdown?.buy?.initial_costs?.upfront_furniture?.toFixed(2)}</Typography>
                    
                    <Typography variant="subtitle2" sx={{ mt: 2 }} gutterBottom>
                      Ongoing Costs
                    </Typography>
                    <Typography>Mortgage Payments: £{results?.cost_breakdown?.buy?.ongoing_costs?.mortgage_payments?.toFixed(2)}</Typography>
                    <Typography>Home Insurance: £{results?.cost_breakdown?.buy?.ongoing_costs?.home_insurance?.toFixed(2)}</Typography>
                    <Typography>Utilities: £{results?.cost_breakdown?.buy?.ongoing_costs?.utilities?.toFixed(2)}</Typography>
                    
                    <Typography variant="subtitle2" sx={{ mt: 2 }} gutterBottom>
                      Selling Costs
                    </Typography>
                    <Typography>Agent Fees: £{results?.cost_breakdown?.buy?.selling_costs?.agent_fees?.toFixed(2)}</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle1" gutterBottom>
                      Rent Scenario Costs
                    </Typography>
                    <Typography>Rent Payments: £{results?.cost_breakdown?.rent?.rent_payments?.toFixed(2)}</Typography>
                    <Typography>Utilities: £{results?.cost_breakdown?.rent?.utilities?.toFixed(2)}</Typography>
                  </Paper>
                </Grid>
              </Grid>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Detailed Cash Flow Analysis
              </Typography>
              <TableContainer component={Paper} sx={{ mt: 2 }}>
                <Table size="small" aria-label="cash flow table">
                  <TableHead>
                    <TableRow>
                      <TableCell>Year</TableCell>
                      <TableCell align="right">Buy Cash Flow (£)</TableCell>
                      <TableCell align="right">Rent Cash Flow (£)</TableCell>
                      <TableCell align="right">Property Value (£)</TableCell>
                      <TableCell align="right">Mortgage Balance (£)</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {results?.cash_flows?.years.map((year, index) => (
                      <TableRow key={year}>
                        <TableCell component="th" scope="row">
                          {year}
                        </TableCell>
                        <TableCell align="right">
                          {results.cash_flows.buy_cash_flow[index].toFixed(2)}
                        </TableCell>
                        <TableCell align="right">
                          {results.cash_flows.rent_cash_flow[index].toFixed(2)}
                        </TableCell>
                        <TableCell align="right">
                          {results.cash_flows.property_value[index].toFixed(2)}
                        </TableCell>
                        <TableCell align="right">
                          {results.cash_flows.mortgage_balance[index].toFixed(2)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Detailed Cash Flow Breakdown
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle1" gutterBottom>
                      Buy Scenario
                    </Typography>
                    {results.cash_flows.buy_breakdown.map((yearData, index) => {
                      const cumulativeTotal = results.cash_flows.buy_breakdown
                        .slice(0, index + 1)
                        .reduce((sum, year) => sum + year.total, 0);
                      return (
                        <Paper key={yearData.year} sx={{ p: 2, mb: 2 }}>
                          <Typography variant="subtitle1" gutterBottom>
                            Year {yearData.year}
                          </Typography>
                          <Grid container spacing={2}>
                            {Object.entries(yearData.components).map(([key, value]) => (
                              <Grid item xs={12} key={key}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="body2">
                                    {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:
                                  </Typography>
                                  <Typography variant="body2">
                                    £{value.toFixed(2)}
                                  </Typography>
                                </Box>
                              </Grid>
                            ))}
                            <Grid item xs={12}>
                              <Divider sx={{ my: 1 }} />
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Typography variant="subtitle2">
                                  Year Total:
                                </Typography>
                                <Typography variant="subtitle2">
                                  £{yearData.total.toFixed(2)}
                                </Typography>
                              </Box>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
                                <Typography variant="subtitle2">
                                  Cumulative Total:
                                </Typography>
                                <Typography variant="subtitle2">
                                  £{cumulativeTotal.toFixed(2)}
                                </Typography>
                              </Box>
                            </Grid>
                          </Grid>
                        </Paper>
                      );
                    })}
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle1" gutterBottom>
                      Rent Scenario
                    </Typography>
                    {results.cash_flows.rent_breakdown.map((yearData, index) => {
                      const cumulativeTotal = results.cash_flows.rent_breakdown
                        .slice(0, index + 1)
                        .reduce((sum, year) => sum + year.total, 0);
                      return (
                        <Paper key={yearData.year} sx={{ p: 2, mb: 2 }}>
                          <Typography variant="subtitle1" gutterBottom>
                            Year {yearData.year}
                          </Typography>
                          <Grid container spacing={2}>
                            {Object.entries(yearData.components).map(([key, value]) => (
                              <Grid item xs={12} key={key}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="body2">
                                    {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:
                                  </Typography>
                                  <Typography variant="body2">
                                    £{value.toFixed(2)}
                                  </Typography>
                                </Box>
                              </Grid>
                            ))}
                            <Grid item xs={12}>
                              <Divider sx={{ my: 1 }} />
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Typography variant="subtitle2">
                                  Year Total:
                                </Typography>
                                <Typography variant="subtitle2">
                                  £{yearData.total.toFixed(2)}
                                </Typography>
                              </Box>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
                                <Typography variant="subtitle2">
                                  Cumulative Total:
                                </Typography>
                                <Typography variant="subtitle2">
                                  £{cumulativeTotal.toFixed(2)}
                                </Typography>
                              </Box>
                            </Grid>
                          </Grid>
                        </Paper>
                      );
                    })}
                  </Paper>
                </Grid>
              </Grid>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Balance Sheet Analysis
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle1" gutterBottom>
                      Buy Scenario Balance Sheet
                    </Typography>
                    {results?.cash_flows?.buy_balance_sheet.map((yearData) => (
                      <Paper key={yearData.year} sx={{ p: 2, mb: 2 }}>
                        <Typography variant="subtitle1" gutterBottom>
                          Year {yearData.year} Balance Sheet
                        </Typography>
                        <Grid container spacing={2}>
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom>
                              Assets
                            </Typography>
                            <Typography>Property Value: £{yearData.assets.property_value.toFixed(2)}</Typography>
                            {yearData.assets.cash !== undefined && (
                              <Typography>Cash from Sale: £{yearData.assets.cash.toFixed(2)}</Typography>
                            )}
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                              Total Assets: £{yearData.assets.total_assets.toFixed(2)}
                            </Typography>
                          </Grid>
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom>
                              Liabilities
                            </Typography>
                            <Typography>Mortgage Balance: £{yearData.liabilities.mortgage_balance.toFixed(2)}</Typography>
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                              Total Liabilities: £{yearData.liabilities.total_liabilities.toFixed(2)}
                            </Typography>
                          </Grid>
                          <Grid item xs={12}>
                            <Typography variant="subtitle2" sx={{ mt: 1, color: yearData.net_worth >= 0 ? 'success.main' : 'error.main' }}>
                              Net Worth: £{yearData.net_worth.toFixed(2)}
                            </Typography>
                          </Grid>
                        </Grid>
                      </Paper>
                    ))}
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle1" gutterBottom>
                      Rent Scenario Balance Sheet
                    </Typography>
                    {results?.cash_flows?.rent_balance_sheet.map((yearData) => (
                      <Paper key={yearData.year} sx={{ p: 2, mb: 2 }}>
                        <Typography variant="subtitle1" gutterBottom>
                          Year {yearData.year} Balance Sheet
                        </Typography>
                        <Grid container spacing={2}>
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom>
                              Assets
                            </Typography>
                            <Typography>Investment Balance: £{yearData.assets.investment_balance.toFixed(2)}</Typography>
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                              Total Assets: £{yearData.assets.total_assets.toFixed(2)}
                            </Typography>
                          </Grid>
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom>
                              Liabilities
                            </Typography>
                            <Typography>Total Liabilities: £{yearData.liabilities.total_liabilities.toFixed(2)}</Typography>
                          </Grid>
                          <Grid item xs={12}>
                            <Typography variant="subtitle2" sx={{ mt: 1, color: yearData.net_worth >= 0 ? 'success.main' : 'error.main' }}>
                              Net Worth: £{yearData.net_worth.toFixed(2)}
                            </Typography>
                          </Grid>
                        </Grid>
                      </Paper>
                    ))}
                  </Paper>
                </Grid>
              </Grid>
            </Box>
          </Paper>
        )}
      </Box>
    </Container>
  );
};

export default App; 