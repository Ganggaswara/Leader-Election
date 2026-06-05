// ============================================
// HELPDESK GUI - MAIN APPLICATION
// ============================================

class HelpdeskApp {
    constructor() {
        this.tickets = [];
        this.currentTicket = null;
        this.clusterPollInterval = null;
        this.init();
    }

    async init() {
        await this.loadConfig();
        this.setupEventListeners();
        await this.loadTickets();
        await this.updateStats();
        await this.loadClusterStatus();
        this.startClusterPolling();
    }

    async loadConfig() {
        try {
            const res = await fetch('/api/config');
            if (res.ok) {
                await res.json();
            }
        } catch (e) {
            console.warn('Config tidak terbaca, tetap pakai proxy /api/backend');
        }
    }

    startClusterPolling() {
        if (this.clusterPollInterval) {
            clearInterval(this.clusterPollInterval);
        }
        this.clusterPollInterval = setInterval(() => this.loadClusterStatus(), 8000);
    }

    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => this.switchView(e));
        });

        // Create Ticket Buttons
        document.getElementById('createTicketBtn').addEventListener('click', () => this.showTicketModal());
        document.getElementById('createTicketBtn2').addEventListener('click', () => this.showTicketModal());

        // Forms
        document.getElementById('ticketForm').addEventListener('submit', (e) => this.handleSaveTicket(e));
        document.getElementById('resolveForm').addEventListener('submit', (e) => this.handleResolveTicket(e));

        // Modals
        document.querySelectorAll('.modal-close, [data-modal]').forEach(btn => {
            btn.addEventListener('click', (e) => this.closeModal(e));
        });

        // Search & Filters
        document.getElementById('searchInput').addEventListener('input', () => this.handleSearch());
        document.getElementById('statusFilter').addEventListener('change', () => this.filterTickets());
        document.getElementById('customerFilter').addEventListener('input', () => this.filterTickets());

        // Refresh Button
        document.querySelector('.btn-icon').addEventListener('click', () => this.refreshData());

        // Sidebar Toggle
        document.getElementById('sidebarToggle')?.addEventListener('click', () => this.toggleSidebar());

        // Modal Overlay Close
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.closeModal(e);
            });
        });
    }

    // ============ VIEW MANAGEMENT ============
    switchView(e) {
        e.preventDefault();
        const view = e.currentTarget.getAttribute('data-view');
        
        // Update nav items
        document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
        e.currentTarget.classList.add('active');

        // Update views
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(`${view}View`).classList.add('active');

        // Update page title
        const titles = { dashboard: 'Dashboard', tickets: 'Tickets', analytics: 'Analytics' };
        document.getElementById('pageTitle').textContent = titles[view];

        if (view === 'tickets') {
            this.loadAllTickets();
        } else if (view === 'analytics') {
            this.loadAnalytics();
        }
    }

    toggleSidebar() {
        document.querySelector('.sidebar').classList.toggle('open');
    }

    // ============ API CALLS ============
    async apiCall(method, endpoint, data = null) {
        try {
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                }
            };

            if (data) {
                options.body = JSON.stringify(data);
            }

            const response = await fetch(`/api/backend${endpoint}`, options);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP Error: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            this.showToast(`Error: ${error.message}`, 'error');
            throw error;
        }
    }

    // ============ TICKET OPERATIONS ============
    async loadTickets() {
        try {
            const response = await this.apiCall('GET', '/tickets');
            this.tickets = response.tickets || [];
            this.displayRecentTickets(this.tickets.slice(0, 5));
        } catch (error) {
            console.error('Error loading tickets:', error);
        }
    }

    async loadAllTickets() {
        try {
            const response = await this.apiCall('GET', '/tickets');
            this.tickets = response.tickets || [];
            this.displayAllTickets(this.tickets);
        } catch (error) {
            console.error('Error loading tickets:', error);
        }
    }

    async createTicket(data) {
        try {
            const response = await this.apiCall('POST', '/tickets', {
                customer_name: data.customerName,
                issue_title: data.issueTitle,
                description: data.description
            });
            
            this.showToast('Ticket created successfully!', 'success');
            this.closeModalById('ticketModal');
            await this.loadTickets();
            await this.updateStats();
        } catch (error) {
            console.error('Error creating ticket:', error);
        }
    }

    async updateTicket(ticketId, data) {
        try {
            const response = await this.apiCall('PUT', `/tickets/${ticketId}`, {
                customer_name: data.customerName,
                issue_title: data.issueTitle,
                description: data.description
            });
            
            this.showToast('Ticket updated successfully!', 'success');
            this.closeModalById('ticketModal');
            await this.loadTickets();
            await this.updateStats();
        } catch (error) {
            console.error('Error updating ticket:', error);
        }
    }

    async resolveTicket(ticketId, resolution) {
        try {
            const response = await this.apiCall('POST', `/tickets/${ticketId}/resolve`, {
                resolution: resolution
            });
            
            this.showToast('Ticket resolved successfully!', 'success');
            this.closeModalById('resolveModal');
            await this.loadTickets();
            await this.updateStats();
        } catch (error) {
            console.error('Error resolving ticket:', error);
        }
    }

    async deleteTicket(ticketId) {
        if (!confirm('Are you sure you want to delete this ticket?')) return;

        try {
            await this.apiCall('DELETE', `/tickets/${ticketId}`);
            this.showToast('Ticket deleted successfully!', 'success');
            await this.loadTickets();
            await this.updateStats();
        } catch (error) {
            console.error('Error deleting ticket:', error);
        }
    }

    // ============ DISPLAY METHODS ============
    displayRecentTickets(tickets) {
        const container = document.getElementById('recentTicketsList');
        
        if (tickets.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-inbox"></i>
                    <p>No tickets yet. Click "New Ticket" to create one.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = tickets.map(ticket => this.createTicketElement(ticket)).join('');
        this.attachTicketListeners();
    }

    displayAllTickets(tickets) {
        const container = document.getElementById('allTicketsList');

        if (tickets.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-search"></i>
                    <p>No tickets found.</p>
                </div>
            `;
            return;
        }

        const html = `
            <table class="table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Customer</th>
                        <th>Issue</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${tickets.map(ticket => `
                        <tr>
                            <td><code>${ticket.ticket_id}</code></td>
                            <td>${ticket.customer_name}</td>
                            <td>${this.truncate(ticket.issue_title, 30)}</td>
                            <td><span class="ticket-status ${ticket.status.toLowerCase()}">${ticket.status}</span></td>
                            <td>${new Date(ticket.created_at).toLocaleDateString()}</td>
                            <td>
                                <button class="btn btn-sm btn-outline view-btn" data-id="${ticket.ticket_id}">
                                    <i class="fas fa-eye"></i>
                                </button>
                                <button class="btn btn-sm btn-danger delete-btn" data-id="${ticket.ticket_id}">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        container.innerHTML = html;
        this.attachTableListeners();
    }

    createTicketElement(ticket) {
        const statusClass = ticket.status.toLowerCase();
        const createdDate = new Date(ticket.created_at).toLocaleDateString();
        
        return `
            <div class="ticket-item" data-id="${ticket.ticket_id}">
                <div class="ticket-header">
                    <span class="ticket-id">${ticket.ticket_id}</span>
                    <span class="ticket-status ${statusClass}">${ticket.status}</span>
                </div>
                <div class="ticket-title">${ticket.issue_title}</div>
                <div class="ticket-meta">
                    <span><strong>Customer:</strong> ${ticket.customer_name}</span>
                    <span><strong>Created:</strong> ${createdDate}</span>
                </div>
                <div class="ticket-footer">
                    ${ticket.status === 'OPEN' ? `
                        <button class="btn btn-sm btn-success resolve-btn" data-id="${ticket.ticket_id}">
                            <i class="fas fa-check"></i> Resolve
                        </button>
                    ` : ''}
                    <button class="btn btn-sm btn-outline view-btn" data-id="${ticket.ticket_id}">
                        <i class="fas fa-eye"></i> View
                    </button>
                </div>
            </div>
        `;
    }

    // ============ MODAL MANAGEMENT ============
    showTicketModal(ticketId = null) {
        // Always show create mode - ignore ticketId parameter
        const modal = document.getElementById('ticketModal');
        const form = document.getElementById('ticketForm');
        const title = document.getElementById('modalTitle');
        const idInput = document.getElementById('ticketId');

        form.reset();
        title.textContent = 'Create New Ticket';
        idInput.value = '';

        modal.classList.add('active');
    }

    showResolveModal(ticketId) {
        const modal = document.getElementById('resolveModal');
        document.getElementById('resolveTicketId').value = ticketId;
        document.getElementById('resolution').value = '';
        modal.classList.add('active');
    }

    async showDetailsModal(ticketId) {
        const ticket = this.tickets.find(t => t.ticket_id === ticketId);
        if (!ticket) return;

        const modal = document.getElementById('detailsModal');
        const container = document.getElementById('ticketDetails');

        const html = `
            <div class="details-row">
                <div class="details-label">Ticket ID:</div>
                <div class="details-value"><code>${ticket.ticket_id}</code></div>
            </div>
            <div class="details-row">
                <div class="details-label">Status:</div>
                <div class="details-value">
                    <span class="ticket-status ${ticket.status.toLowerCase()}">${ticket.status}</span>
                </div>
            </div>
            <div class="details-row">
                <div class="details-label">Customer:</div>
                <div class="details-value">${ticket.customer_name}</div>
            </div>
            <div class="details-row">
                <div class="details-label">Issue Title:</div>
                <div class="details-value">${ticket.issue_title}</div>
            </div>
            <div class="details-row">
                <div class="details-label">Description:</div>
                <div class="details-value">${ticket.description}</div>
            </div>
            <div class="details-row">
                <div class="details-label">Resolution:</div>
                <div class="details-value">${ticket.resolution || 'Pending'}</div>
            </div>
            <div class="details-row">
                <div class="details-label">Created:</div>
                <div class="details-value">${new Date(ticket.created_at).toLocaleString()}</div>
            </div>
            ${ticket.updated_at ? `
                <div class="details-row">
                    <div class="details-label">Updated:</div>
                    <div class="details-value">${new Date(ticket.updated_at).toLocaleString()}</div>
                </div>
            ` : ''}
            <div class="details-actions">
                ${ticket.status === 'OPEN' ? `
                    <button class="btn btn-success resolve-btn" data-id="${ticket.ticket_id}">
                        <i class="fas fa-check"></i> Resolve Ticket
                    </button>
                ` : ''}
                <button class="btn btn-outline" onclick="app.closeModal(event)">Close</button>
            </div>
        `;

        container.innerHTML = html;
        modal.classList.add('active');

        // Attach resolve button listener
        const resolveBtn = container.querySelector('.resolve-btn');
        if (resolveBtn) {
            resolveBtn.addEventListener('click', () => {
                this.closeModalById('detailsModal');
                this.showResolveModal(ticketId);
            });
        }
    }

    closeModal(e) {
        const modalId = e.currentTarget.getAttribute('data-modal');
        this.closeModalById(modalId);
    }

    closeModalById(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) modal.classList.remove('active');
    }

    // ============ EVENT HANDLERS ============
    handleSaveTicket(e) {
        e.preventDefault();
        const data = {
            customerName: document.getElementById('customerName').value,
            issueTitle: document.getElementById('issueTitle').value,
            description: document.getElementById('description').value
        };

        // Always create new ticket (no edit mode)
        this.createTicket(data);
    }

    handleResolveTicket(e) {
        e.preventDefault();
        const ticketId = document.getElementById('resolveTicketId').value;
        const resolution = document.getElementById('resolution').value;
        this.resolveTicket(ticketId, resolution);
    }

    handleSearch() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const filtered = this.tickets.filter(ticket =>
            ticket.ticket_id.toLowerCase().includes(searchTerm) ||
            ticket.customer_name.toLowerCase().includes(searchTerm) ||
            ticket.issue_title.toLowerCase().includes(searchTerm)
        );
        this.displayRecentTickets(filtered.slice(0, 5));
    }

    filterTickets() {
        const status = document.getElementById('statusFilter').value;
        const customer = document.getElementById('customerFilter').value.toLowerCase();

        let filtered = this.tickets;

        if (status) {
            filtered = filtered.filter(t => t.status === status);
        }

        if (customer) {
            filtered = filtered.filter(t =>
                t.customer_name.toLowerCase().includes(customer)
            );
        }

        this.displayAllTickets(filtered);
        this.attachTableListeners();
    }

    attachTicketListeners() {
        document.querySelectorAll('.resolve-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const ticketId = e.currentTarget.getAttribute('data-id');
                this.showResolveModal(ticketId);
            });
        });

        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const ticketId = e.currentTarget.getAttribute('data-id');
                this.showDetailsModal(ticketId);
            });
        });
    }

    attachTableListeners() {
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const ticketId = e.currentTarget.getAttribute('data-id');
                this.showDetailsModal(ticketId);
            });
        });

        document.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const ticketId = e.currentTarget.getAttribute('data-id');
                this.deleteTicket(ticketId);
            });
        });
    }

    // ============ CLUSTER STATUS ============
    async loadClusterStatus() {
        const container = document.getElementById('clusterNodesList');
        try {
            const res = await fetch('/api/cluster/status');
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            const data = await res.json();
            this.renderClusterStatus(data);
        } catch (error) {
            console.error('Cluster status error:', error);
            if (container) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-plug"></i>
                        <p>Tidak dapat terhubung ke kluster. Pastikan backend berjalan.</p>
                    </div>
                `;
            }
            document.getElementById('activeLeaderName').textContent = 'Tidak tersedia';
            document.getElementById('clusterUpdatedAt').textContent = 'Gagal memuat';
        }
    }

    renderClusterStatus(data) {
        const leaderBanner = document.getElementById('leaderBanner');
        const leaderNameEl = document.getElementById('activeLeaderName');
        const electionBadge = document.getElementById('electionBadge');
        const workersList = document.getElementById('activeWorkersList');
        const updatedAt = document.getElementById('clusterUpdatedAt');
        const container = document.getElementById('clusterNodesList');

        const leader = data.leader;
        const inElection = data.election_in_progress;
        const nodes = data.nodes || [];
        const activeWorkers = data.active_workers || [];

        if (leader && leader.node_name) {
            leaderNameEl.textContent = `${leader.node_name} (ID: ${leader.node_id})`;
            leaderBanner.classList.remove('no-leader');
        } else {
            leaderNameEl.textContent = inElection ? 'Pemilu sedang berlangsung...' : 'Belum ada leader';
            leaderBanner.classList.add('no-leader');
        }

        electionBadge.classList.toggle('hidden', !inElection);

        if (activeWorkers.length > 0) {
            workersList.innerHTML = activeWorkers.map(name => `
                <span class="chip chip-active">
                    <i class="fas fa-bolt"></i> ${name}
                </span>
            `).join('');
        } else {
            const readyWorkers = nodes.filter(n => n.online && n.rabbitmq_connected);
            if (readyWorkers.length > 0) {
                workersList.innerHTML = readyWorkers.map(n => `
                    <span class="chip chip-muted">
                        <i class="fas fa-circle"></i> ${n.node_name} (siaga)
                    </span>
                `).join('');
            } else {
                workersList.innerHTML = '<span class="chip chip-muted">Belum ada worker online</span>';
            }
        }

        if (data.updated_at) {
            updatedAt.textContent = `Diperbarui: ${new Date(data.updated_at * 1000).toLocaleTimeString('id-ID')}`;
        }

        if (nodes.length === 0) {
            container.innerHTML = '<p class="text-center">Tidak ada node terdaftar.</p>';
            return;
        }

        container.innerHTML = nodes.map(node => {
            const online = node.online;
            const isLeader = node.is_leader;
            const workerBusy = node.worker_active;
            const cardClass = [
                'node-card',
                online ? 'online' : 'offline',
                isLeader ? 'is-leader' : '',
                workerBusy ? 'worker-busy' : '',
            ].filter(Boolean).join(' ');

            const badges = [];
            if (!online) {
                badges.push('<span class="node-badge offline">Offline</span>');
            } else if (isLeader) {
                badges.push('<span class="node-badge leader"><i class="fas fa-crown"></i> Leader</span>');
            } else {
                badges.push('<span class="node-badge follower">Follower</span>');
            }
            if (workerBusy) {
                badges.push('<span class="node-badge worker"><i class="fas fa-bolt"></i> Memproses</span>');
            }
            if (node.rabbitmq_connected) {
                badges.push('<span class="node-badge rmq">RabbitMQ</span>');
            }

            const meta = online
                ? `ID ${node.node_id} · ${node.resolved_count ?? 0} tiket diproses`
                : 'Node tidak merespons';

            return `
                <div class="${cardClass}">
                    <div class="node-card-header">
                        <span class="node-card-name">${node.node_name || 'Unknown'}</span>
                        <span class="node-status-dot ${online ? 'online' : ''}"></span>
                    </div>
                    <div class="node-badges">${badges.join('')}</div>
                    <div class="node-meta">${meta}</div>
                </div>
            `;
        }).join('');
    }

    // ============ STATISTICS ============
    async updateStats() {
        const openCount = this.tickets.filter(t => t.status === 'OPEN').length;
        const resolvedCount = this.tickets.filter(t => t.status === 'RESOLVED').length;
        const failedCount = this.tickets.filter(t => t.status === 'FAILED_TO_RESOLVE').length;
        const totalCount = this.tickets.length;

        document.getElementById('openTicketsCount').textContent = openCount;
        document.getElementById('resolvedTicketsCount').textContent = resolvedCount;
        document.getElementById('failedTicketsCount').textContent = failedCount;
        document.getElementById('totalTicketsCount').textContent = totalCount;
    }

    async loadAnalytics() {
        // Placeholder for analytics - can be enhanced later
        console.log('Loading analytics...');
    }

    // ============ UTILITIES ============
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const icons = {
            success: 'fa-check-circle',
            error: 'fa-times-circle',
            info: 'fa-info-circle'
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <i class="fas ${icons[type]} toast-icon"></i>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    truncate(str, length) {
        return str.length > length ? str.substring(0, length) + '...' : str;
    }

    async refreshData() {
        await this.loadTickets();
        await this.updateStats();
        await this.loadClusterStatus();
        this.showToast('Data diperbarui!', 'success');
    }
}

// ============================================
// INITIALIZE APP
// ============================================
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new HelpdeskApp();
});
