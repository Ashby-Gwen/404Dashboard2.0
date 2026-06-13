# Syluxent ERP System - Flask Version

A comprehensive Enterprise Resource Planning system built with Flask and SQLite database, converted from the original Firebase-based implementation.

## Features

### Core Functionality
- **User Authentication**: Role-based login system (Admin, Manager, Staff)
- **Sales Order Management**: Excel upload with auto-identification of fields
- **Invoice Processing**: Sales and Service invoices with 2307 tax checker
- **Purchase Order Management**: Expense tracking with 16 debit account types
- **Analytics Dashboard**: Revenue tracking, cashflow analysis, and leakage detection
- **Database Interface**: Complete admin control over all data tables

### Technical Features
- **Flask Backend**: RESTful API with SQLAlchemy ORM
- **SQLite Database**: Local data storage with full schema
- **Excel Integration**: Client-side processing with field auto-identification
- **Real-time Updates**: Live dashboard with current date/time
- **Responsive Design**: Mobile-friendly interface with modern UI
- **Safety Features**: 5-second confirmation buffer for critical actions

## Documentation

- [System Test Analysis](docs/SYSTEM_TEST_ANALYSIS.md): Current compliance status, known gaps, and verification checklist for the documented ERP requirements.
- [Deployment Suggestions](docs/DEPLOYMENT_SUGGESTIONS.md): Practical deployment options for the Flask, SQLite, pandas, and Chart.js stack used by this project.

## Installation & Setup

(for dev): python -m venv venv

### Prerequisites
- Python 3.8+
- pip package manager

### Installation Steps
1. **Clone/Download the project**
   ```bash
   cd Syluxent-Copy
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize database**
   ```bash
   python app.py
   ```
   The app will automatically create the SQLite database and default admin user.

### Default Login
- **Username**: admin
- **Password**: admin123
- **Role**: Administrator

## Project Structure

```
Syluxent-Copy/
├── app.py                 # Main Flask application
├── requirements.txt         # Python dependencies
├── templates/             # HTML templates
│   ├── landing.html       # Landing page
│   ├── login.html         # Login/Register page
│   ├── dashboard.html     # Main dashboard
│   ├── sales_orders.html  # Sales order management
│   ├── invoices.html      # Invoice processing
│   ├── purchase_orders.html # Purchase order management
│   ├── admin.html         # Database interface
│   └── manager.html      # Analytics dashboard
└── static/
    └── css/
        └── styles.css     # Styling
```

## Database Schema

The system uses SQLite with the following main tables:

- **users**: User accounts with role assignments
- **roles**: User role definitions (admin, manager, staff)
- **clients**: Client information and contact details
- **sales_orders**: Sales order headers and details
- **sales_order_items**: Line items for sales orders
- **invoices**: Invoice records with payment tracking
- **purchase_orders**: Expense and purchase order records
- **purchase_order_debits**: Debit account assignments

## User Roles & Permissions

### Administrator
- Full access to all modules
- User management and role assignments
- Database interface access
- Complete data manipulation

### Manager
- Dashboard access with analytics
- View all business reports
- Revenue and performance tracking
- No data modification capabilities

### Staff
- Sales order creation and management
- Invoice processing and payment tracking
- Purchase order entry
- Operational task management

## Key Features

### Excel Processing (Sales Orders)
- **Drag & Drop Upload**: Intuitive file upload interface
- **Auto-Identification**: Automatic field detection for:
  - SO Numbers
  - Company Names
  - Store Names/Branches
  - Order Dates
- **Manual Override**: Edit identified fields directly in spreadsheet
- **Data Validation**: Ensures data integrity before processing

### Invoice Management
- **Dual Invoice Types**: Sales Invoice (SI-) and Service Invoice (SVI-)
- **2307 Tax Checker**: Toggle for tax inclusion in calculations
- **Safety Buffer**: 5-second countdown for critical confirmations
- **Entry Duplication**: Quick reuse of previous invoice data
- **Payment Tracking**: Downpayment and full payment options

### Purchase Orders
- **16 Debit Types**: Comprehensive expense categorization
- **Automatic Calculations**: Net balance computation
- **Required Field Validation**: Ensures complete data entry
- **Multiple Debits**: Support for complex expense allocations

### Analytics & Reporting
- **Revenue Leakage Detection**: Identifies high-impact clients
- **Cash Flow Analysis**: Weekly and monthly tracking
- **Performance Metrics**: Sales and invoice analytics
- **Client Insights**: Revenue breakdown by client
- **Period Selection**: Week, month, quarter, year views

## Deployment

### Development Server
```bash
python app.py
```
Access at: http://localhost:5000

### Production Deployment
For production deployment, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Environment Variables
- `SECRET_KEY`: Flask secret key for sessions
- `DATABASE_URL`: SQLite database path (optional, defaults to `syluxent.db`)

## Security Features

- **Session Management**: Secure user sessions
- **Role-Based Access**: Permission enforcement by user role
- **Input Validation**: Server-side data validation
- **SQL Injection Protection**: SQLAlchemy ORM prevents SQL injection
- **CSRF Protection**: Flask-WTF integration (if implemented)

## Browser Compatibility

- **Modern Browsers**: Chrome, Firefox, Safari, Edge (latest versions)
- **Mobile Responsive**: Works on tablets and smartphones
- **JavaScript Required**: Modern features need JavaScript enabled

## Data Backup & Recovery

### SQLite Database
- **Location**: `syluxent.db` in project root
- **Backup**: Simply copy the database file
- **Recovery**: Replace the database file with backup

### Recommended Backup Schedule
- **Daily**: Automated database file copy
- **Weekly**: Full system backup
- **Monthly**: Archive to external storage

## Troubleshooting

### Common Issues
1. **Database Lock**: Restart the application
2. **Excel Upload Failures**: Check file format (.xlsx required)
3. **Login Issues**: Verify default admin credentials
4. **Analytics Not Loading**: Check data exists in system

### Debug Mode
Development mode includes:
- Detailed error messages
- Debug toolbar
- Auto-reload on code changes

## API Endpoints

### Authentication
- `POST /login` - User login
- `POST /register` - User registration
- `GET /logout` - User logout

### Sales Orders
- `GET /sales-orders` - Sales order page
- `POST /upload-excel` - Excel file processing
- `POST /auto-identify-fields` - Field auto-detection
- `POST /create-sales-order` - Create new sales order

### Invoices
- `GET /invoices` - Invoice management page
- `GET /get-invoices` - Fetch invoice data
- `POST /create-invoice` - Create new invoice

### Purchase Orders
- `GET /purchase-orders` - Purchase order page
- `GET /get-purchase-orders` - Fetch purchase order data
- `POST /create-purchase-order` - Create new purchase order

### Admin Interface
- `GET /database-interface` - Admin dashboard
- `GET /get-users` - User management data
- `GET /get-roles` - Role management data
- `GET /get-clients` - Client management data

### Analytics
- `GET /analytics` - Analytics dashboard
- `GET /get-analytics` - Analytics data API

## Support & Maintenance

### Performance Optimization
- **Database Indexing**: Automatic on frequently accessed fields
- **Query Optimization**: Efficient SQLAlchemy queries
- **Asset Caching**: Static file optimization

### Scaling Considerations
- **Database Size**: Monitor SQLite file size
- **User Load**: Consider connection pooling for high traffic
- **Backup Strategy**: Implement automated backup system

## License

This project maintains the original business logic and interface design while modernizing the technology stack from Firebase to Flask with SQLite.

## Future Enhancements

- **API Documentation**: Swagger/OpenAPI integration
- **Advanced Analytics**: Machine learning for predictions
- **Mobile App**: Native mobile application
- **Cloud Deployment**: Docker containerization
- **Email Notifications**: Automated alerts and reports
