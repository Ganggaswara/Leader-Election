# Helpdesk GUI - Modern Interactive Interface

Ini adalah web-based GUI untuk Helpdesk System dengan design modern, responsif, dan interaktif.

## Features 🎨

✨ **Modern Design**

- Sleek gradient sidebar dengan smooth navigation
- Responsive layout yang cocok untuk desktop & mobile
- Smooth animations dan transitions
- Modern color scheme dengan professional vibes

🚀 **Interactive Features**

- Real-time ticket management (Create, Read, Update, Delete)
- Quick resolve tickets dengan modal dialog
- Search & filter functionality
- Status indicators dengan warna-warna intuitif
- Toast notifications untuk user feedback

📊 **Dashboard**

- Stats overview (Open, Resolved, Failed, Total tickets)
- Recent tickets list
- Quick actions buttons

📋 **Ticket Management**

- List semua tickets dalam table format
- View ticket details secara lengkap
- Edit open tickets
- Delete tickets
- Resolve tickets dengan resolution notes
- Filter by status & customer

📱 **Responsive**

- Mobile-friendly layout
- Touch-friendly buttons
- Collapsible sidebar untuk mobile

## Installation & Setup

### 1. Install Dependencies

```bash
cd GUI
pip install -r requirements.txt
```

### 2. Configure API URL

Edit `app.py` dan sesuaikan `API_BASE_URL`:

```python
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
```

Atau set environment variable:

```bash
export API_BASE_URL=http://localhost:8000
```

### 3. Run the GUI

```bash
python app.py
```

GUI akan berjalan di: **http://localhost:5000**

## API Endpoints

GUI ini connect ke backend API endpoints:

- `GET /tickets` - List semua tickets
- `POST /tickets` - Create ticket baru
- `GET /tickets/{ticket_id}` - Get ticket detail
- `PUT /tickets/{ticket_id}` - Update ticket
- `DELETE /tickets/{ticket_id}` - Delete ticket
- `POST /tickets/{ticket_id}/resolve` - Resolve ticket

## Project Structure

```
GUI/
├── app.py                          # Flask server
├── requirements.txt                # Dependencies
├── static/
│   ├── css/
│   │   └── style.css              # Modern styling
│   └── js/
│       └── main.js                # Interactive logic
├── templates/
│   └── index.html                 # Main HTML
└── README.md                       # This file
```

## Technologies Used

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JavaScript (No framework, very lightweight!)
- **Styling**: Custom CSS3 dengan modern design patterns
- **Icons**: Font Awesome 6
- **APIs**: REST API calls

## Usage Guide

### Dashboard

- Lihat overview statistics
- Quick view recent tickets
- Navigation yang mudah

### Create Ticket

1. Click "New Ticket" button
2. Isi form dengan customer name, issue title, dan description
3. Click "Save Ticket"

### Edit Ticket

1. Go ke Tickets view
2. Click edit button pada ticket yang ingin diubah
3. Update data dan save

### Resolve Ticket

1. Click resolve button pada ticket
2. Masukkan resolution details
3. Click "Mark as Resolved"

### View Ticket Details

1. Click view/eye button pada ticket
2. Lihat semua informasi lengkap
3. Bisa langsung resolve dari detail view

### Search & Filter

- Use search box di top untuk quick search
- Use status filter untuk filter by status
- Use customer filter untuk filter by customer name

## UI Features

🎯 **Color Coding**

- Blue: Open tickets
- Green: Resolved tickets
- Red: Failed tickets

💫 **Smooth Interactions**

- Hover effects pada semua interactive elements
- Loading states untuk async operations
- Toast notifications untuk feedback
- Modal dialogs untuk forms

📐 **Responsive Breakpoints**

- Desktop (> 1024px)
- Tablet (768px - 1024px)
- Mobile (< 768px)

## Tips & Tricks

💡 **Pro Tips**

- Gunakan Ctrl+K atau search box untuk quick search
- Double-click ticket untuk view details
- Sidebar bisa di-collapse di mobile
- All data real-time update

## Troubleshooting

**GUI tidak bisa connect ke API?**

- Pastikan ticket_service.py running di port 8000
- Check API_BASE_URL di app.py

**CSS/JS tidak load?**

- Clear browser cache (Ctrl+Shift+Delete)
- Make sure files ada di static/ folder

**Styling looks weird?**

- Try different browser (Chrome/Firefox recommended)
- Check browser console untuk errors

## Future Enhancements 🚀

- Real-time updates dengan WebSockets
- Export tickets to PDF/CSV
- Advanced analytics & reporting
- User authentication & roles
- Ticket categories & tags
- Email notifications
- Bulk operations

---

Developed with ❤️ untuk Helpdesk System
