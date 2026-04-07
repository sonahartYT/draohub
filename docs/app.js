/* ============================================================
   DracoHub Careers — Frontend Application
   Fetches jobs from Supabase, renders cards, handles
   search/filter/sort, upvoting, dark mode, and the detail modal.
   ============================================================ */

// --- Configuration ---
const SUPABASE_URL = 'https://ljhbyudaiuhviagiigwb.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxqaGJ5dWRhaXVodmlhZ2lpZ3diIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU1ODE4NTgsImV4cCI6MjA5MTE1Nzg1OH0.N6eQLAmrTqidXYZRej_Eqpy5G_ci6mLRZ64OW1XEHkE';
const PAGE_SIZE = 12;

// --- State ---
let allJobs = [];
let filteredJobs = [];
let displayCount = PAGE_SIZE;

// --- Upvote tracking (localStorage) ---
function getVotedIds() {
    try {
        return new Set(JSON.parse(localStorage.getItem('dracohub-votes') || '[]'));
    } catch { return new Set(); }
}
function saveVotedId(id) {
    const voted = getVotedIds();
    voted.add(id);
    localStorage.setItem('dracohub-votes', JSON.stringify([...voted]));
}
function removeVotedId(id) {
    const voted = getVotedIds();
    voted.delete(id);
    localStorage.setItem('dracohub-votes', JSON.stringify([...voted]));
}
function hasVoted(id) {
    return getVotedIds().has(id);
}

// --- DOM refs ---
const jobsGrid = document.getElementById('jobsGrid');
const searchInput = document.getElementById('searchInput');
const filterSource = document.getElementById('filterSource');
const filterLocation = document.getElementById('filterLocation');
const filterSort = document.getElementById('filterSort');
const resultsCount = document.getElementById('resultsCount');
const loadMoreWrap = document.getElementById('loadMoreWrap');
const loadMoreBtn = document.getElementById('loadMoreBtn');
const emptyState = document.getElementById('emptyState');
const modalOverlay = document.getElementById('modalOverlay');
const modalBody = document.getElementById('modalBody');
const modalClose = document.getElementById('modalClose');
const themeToggle = document.getElementById('themeToggle');
const mobileMenuBtn = document.getElementById('mobileMenuBtn');
const mobileMenu = document.getElementById('mobileMenu');
const statJobs = document.getElementById('statJobs');
const statCompanies = document.getElementById('statCompanies');
const disclaimer = document.getElementById('disclaimer');
const disclaimerClose = document.getElementById('disclaimerClose');

// --- Supabase helpers ---
const supaHeaders = {
    'apikey': SUPABASE_KEY,
    'Authorization': `Bearer ${SUPABASE_KEY}`,
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
};

async function fetchJobs() {
    const url = `${SUPABASE_URL}/rest/v1/raw_jobs?select=*&order=created_at.desc`;
    const res = await fetch(url, { headers: supaHeaders });
    if (!res.ok) throw new Error(`Supabase error: ${res.status}`);
    return res.json();
}

async function upvoteJob(jobId) {
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;

    const alreadyVoted = hasVoted(jobId);

    // Optimistic UI update
    if (alreadyVoted) {
        job.upvotes = Math.max((job.upvotes || 0) - 1, 0);
        removeVotedId(jobId);
    } else {
        job.upvotes = (job.upvotes || 0) + 1;
        saveVotedId(jobId);
    }
    renderJobs();
    updateModalUpvoteBtn(jobId);

    // Persist to Supabase
    try {
        const readRes = await fetch(
            `${SUPABASE_URL}/rest/v1/raw_jobs?select=upvotes&id=eq.${jobId}`,
            { headers: supaHeaders }
        );
        const rows = await readRes.json();
        const current = (rows[0]?.upvotes || 0);
        const newValue = alreadyVoted ? Math.max(current - 1, 0) : current + 1;

        await fetch(
            `${SUPABASE_URL}/rest/v1/raw_jobs?id=eq.${jobId}`,
            {
                method: 'PATCH',
                headers: supaHeaders,
                body: JSON.stringify({ upvotes: newValue }),
            }
        );
    } catch (err) {
        console.error('Upvote toggle failed:', err);
    }
}

// --- Init ---
async function init() {
    try {
        allJobs = await fetchJobs();
        populateLocationFilter();
        updateStats();
        applyFilters();
        initScrollAnimations();
        initDisclaimer();
    } catch (err) {
        console.error('Failed to load jobs:', err);
        jobsGrid.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:var(--text-muted);">Unable to load jobs. Please try again later.</p>';
    }
}

// --- Disclaimer ---
function initDisclaimer() {
    if (localStorage.getItem('dracohub-disclaimer-dismissed')) {
        disclaimer.classList.add('hidden');
    }
}

// --- Stats ---
function updateStats() {
    statJobs.textContent = allJobs.length;
    const companies = new Set(allJobs.map(j => j.company).filter(Boolean));
    statCompanies.textContent = companies.size;
}

// --- Location Filter ---
function populateLocationFilter() {
    const locations = new Set();
    allJobs.forEach(job => {
        if (job.location) {
            const parts = job.location.split(',').map(s => s.trim());
            if (parts.length >= 2) {
                locations.add(parts[0]);
            } else if (parts[0]) {
                locations.add(parts[0]);
            }
        }
    });
    const sorted = [...locations].sort();
    sorted.forEach(loc => {
        const opt = document.createElement('option');
        opt.value = loc;
        opt.textContent = loc;
        filterLocation.appendChild(opt);
    });
}

// --- Filter & Render ---
function applyFilters() {
    const query = searchInput.value.toLowerCase().trim();
    const source = filterSource.value;
    const location = filterLocation.value.toLowerCase();
    const sort = filterSort.value;

    filteredJobs = allJobs.filter(job => {
        if (query) {
            const searchable = `${job.job_title} ${job.company} ${job.location} ${job.description}`.toLowerCase();
            if (!searchable.includes(query)) return false;
        }
        if (source && job.source !== source) return false;
        if (location && !(job.location || '').toLowerCase().includes(location)) return false;
        return true;
    });

    // Sort
    if (sort === 'newest') {
        filteredJobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    } else if (sort === 'oldest') {
        filteredJobs.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    } else if (sort === 'upvotes') {
        filteredJobs.sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0));
    } else if (sort === 'company') {
        filteredJobs.sort((a, b) => (a.company || '').localeCompare(b.company || ''));
    }

    displayCount = PAGE_SIZE;
    renderJobs();
}

// --- Upvote button HTML ---
function upvoteBtnHtml(jobId, count, extraClass) {
    const voted = hasVoted(jobId);
    return `
        <button class="upvote-btn ${voted ? 'voted' : ''} ${extraClass || ''}"
                onclick="event.stopPropagation(); upvoteJob(${jobId})"
                ${voted ? 'title="You upvoted this"' : 'title="Upvote this listing"'}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="${voted ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
            <span class="upvote-count">${count || 0}</span>
        </button>
    `;
}

function renderJobs() {
    const visible = filteredJobs.slice(0, displayCount);

    if (visible.length === 0) {
        jobsGrid.innerHTML = '';
        emptyState.style.display = 'block';
        loadMoreWrap.style.display = 'none';
        resultsCount.textContent = 'No jobs found.';
        return;
    }

    emptyState.style.display = 'none';
    resultsCount.textContent = `Showing ${visible.length} of ${filteredJobs.length} jobs`;

    jobsGrid.innerHTML = visible.map((job, i) => `
        <div class="job-card fade-in" onclick="openModal(${job.id})" style="animation-delay:${Math.min(i * 0.05, 0.3)}s">
            <div class="job-card-header">
                <span class="job-card-source">${escapeHtml(job.source)}</span>
                <h3 class="job-card-title">${escapeHtml(job.job_title)}</h3>
                <p class="job-card-company">${escapeHtml(job.company || 'Company not listed')}</p>
            </div>
            <div class="job-card-meta">
                ${job.location ? `<span>${escapeHtml(job.location)}</span>` : ''}
                ${job.date_posted ? `<span>${formatDate(job.date_posted)}</span>` : ''}
            </div>
            <p class="job-card-desc">${escapeHtml(truncate(job.description, 160))}</p>
            <div class="job-card-actions">
                ${upvoteBtnHtml(job.id, job.upvotes)}
                <div class="job-card-buttons">
                    <button class="btn btn-secondary" onclick="event.stopPropagation(); openModal(${job.id})">View Details</button>
                    ${job.apply_url ? `<a href="${escapeHtml(job.apply_url)}" target="_blank" rel="noopener" class="btn btn-primary" onclick="event.stopPropagation()">Apply</a>` : ''}
                </div>
            </div>
        </div>
    `).join('');

    // Trigger fade-in
    requestAnimationFrame(() => {
        document.querySelectorAll('.job-card.fade-in').forEach(el => el.classList.add('visible'));
    });

    // Load more button
    loadMoreWrap.style.display = displayCount < filteredJobs.length ? 'block' : 'none';
}

// --- Modal ---
function openModal(jobId) {
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;

    modalBody.innerHTML = `
        <span class="modal-source">${escapeHtml(job.source)}</span>
        <h2 class="modal-title">${escapeHtml(job.job_title)}</h2>
        <p class="modal-company">${escapeHtml(job.company || 'Company not listed')}</p>
        <div class="modal-meta">
            ${job.location ? `<span>${escapeHtml(job.location)}</span>` : ''}
            ${job.date_posted ? `<span>Posted: ${formatDate(job.date_posted)}</span>` : ''}
        </div>
        <div class="modal-desc">${escapeHtml(job.description || 'No description available.')}</div>
        <div class="modal-actions" id="modalActions">
            ${upvoteBtnHtml(job.id, job.upvotes)}
            ${job.apply_url ? `<a href="${escapeHtml(job.apply_url)}" target="_blank" rel="noopener" class="btn btn-primary modal-apply">Apply Now</a>` : ''}
        </div>
    `;

    modalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function updateModalUpvoteBtn(jobId) {
    const actions = document.getElementById('modalActions');
    if (!actions) return;
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;
    const btn = actions.querySelector('.upvote-btn');
    if (btn) {
        btn.classList.add('voted');
        btn.querySelector('.upvote-count').textContent = job.upvotes || 0;
    }
}

function closeModal() {
    modalOverlay.classList.remove('open');
    document.body.style.overflow = '';
}

// --- Dark Mode ---
function initTheme() {
    const stored = localStorage.getItem('dracohub-theme');
    if (stored) {
        document.documentElement.setAttribute('data-theme', stored);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('dracohub-theme', next);
}

// --- Mobile Menu ---
function toggleMobileMenu() {
    mobileMenu.classList.toggle('open');
}

// --- Scroll Animations ---
function initScrollAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.feature-card, .about-text, .subscribe-card').forEach(el => {
        el.classList.add('fade-in');
        observer.observe(el);
    });
}

// --- Helpers ---
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
        return dateStr;
    }
}

function debounce(fn, ms) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

// --- Event Listeners ---
searchInput.addEventListener('input', debounce(applyFilters, 300));
filterSource.addEventListener('change', applyFilters);
filterLocation.addEventListener('change', applyFilters);
filterSort.addEventListener('change', applyFilters);
loadMoreBtn.addEventListener('click', () => {
    displayCount += PAGE_SIZE;
    renderJobs();
});
modalClose.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) closeModal();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});
themeToggle.addEventListener('click', toggleTheme);
mobileMenuBtn.addEventListener('click', toggleMobileMenu);
disclaimerClose.addEventListener('click', () => {
    disclaimer.classList.add('hidden');
    localStorage.setItem('dracohub-disclaimer-dismissed', '1');
});

// Close mobile menu on link click
document.querySelectorAll('.mobile-menu-link').forEach(link => {
    link.addEventListener('click', () => mobileMenu.classList.remove('open'));
});

// --- Boot ---
initTheme();
init();
