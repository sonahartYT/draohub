/* ============================================================
   DracoHub Careers — Frontend Application
   Fetches jobs from Supabase, renders cards, handles search/
   filter/sort, upvoting, sharing, collections, dark mode,
   and the detail modal.
   ============================================================ */

// --- Configuration ---
const SUPABASE_URL = 'https://ljhbyudaiuhviagiigwb.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxqaGJ5dWRhaXVodmlhZ2lpZ3diIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU1ODE4NTgsImV4cCI6MjA5MTE1Nzg1OH0.N6eQLAmrTqidXYZRej_Eqpy5G_ci6mLRZ64OW1XEHkE';
const FLW_PUBLIC_KEY = 'FLWPUBK_TEST-0cb85e69f14033272d573902cfc31c9e-X';

const PAGE_SIZE = 12;
const SITE_URL = window.location.origin + window.location.pathname;

// --- State ---
let allJobs = [];
let filteredJobs = [];
let displayCount = PAGE_SIZE;
let modalViewCount = 0; // tracks job detail views for nudge
let showStale = false;  // whether to show listings older than 30 days
let staleCount = 0;     // count of listings hidden by date filter

// ============================================================
// LOCALSTORAGE HELPERS
// ============================================================
function getVotedIds() {
    try { return new Set(JSON.parse(localStorage.getItem('dracohub-votes') || '[]')); }
    catch { return new Set(); }
}
function saveVotedId(id) {
    const v = getVotedIds(); v.add(id);
    localStorage.setItem('dracohub-votes', JSON.stringify([...v]));
}
function removeVotedId(id) {
    const v = getVotedIds(); v.delete(id);
    localStorage.setItem('dracohub-votes', JSON.stringify([...v]));
}
function hasVoted(id) { return getVotedIds().has(id); }

function getFlaggedIds() {
    try { return new Set(JSON.parse(localStorage.getItem('dracohub-flagged') || '[]')); }
    catch { return new Set(); }
}
function saveFlaggedId(id) {
    const f = getFlaggedIds(); f.add(id);
    localStorage.setItem('dracohub-flagged', JSON.stringify([...f]));
}
function hasFlagged(id) { return getFlaggedIds().has(id); }

function getSavedIds() {
    try { return new Set(JSON.parse(localStorage.getItem('dracohub-saved') || '[]')); }
    catch { return new Set(); }
}
function toggleSaved(id) {
    const s = getSavedIds();
    if (s.has(id)) s.delete(id); else s.add(id);
    localStorage.setItem('dracohub-saved', JSON.stringify([...s]));
    updateCollectionBar();
    renderJobs();
}
function isSaved(id) { return getSavedIds().has(id); }

// ============================================================
// DOM REFS
// ============================================================
const jobsGrid = document.getElementById('jobsGrid');
const searchInput = document.getElementById('searchInput');
const filterSource = document.getElementById('filterSource');
const filterCategory = document.getElementById('filterCategory');
const filterSeniority = document.getElementById('filterSeniority');
const filterEmployment = document.getElementById('filterEmployment');
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
const shareNudge = document.getElementById('shareNudge');
const shareNudgeClose = document.getElementById('shareNudgeClose');
const collectionBar = document.getElementById('collectionBar');
const collectionCount = document.getElementById('collectionCount');

// ============================================================
// SUPABASE
// ============================================================
const supaHeaders = {
    'apikey': SUPABASE_KEY,
    'Authorization': `Bearer ${SUPABASE_KEY}`,
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
};

async function fetchJobs() {
    const res = await fetch('./jobs.json');
    if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.status}`);
    return res.json();
}

// ============================================================
// SHARING HELPERS
// ============================================================
function shareText(job) {
    return `${job.job_title}${job.company ? ' at ' + job.company : ''}${job.location ? ' — ' + job.location : ''}. Found on DracoHub Careers`;
}

function shareUrl(job) {
    return `${SITE_URL}?job=${job.id}`;
}

function shareBtnsHtml(job, size) {
    const s = size || 16;
    const text = encodeURIComponent(shareText(job));
    const url = encodeURIComponent(shareUrl(job));
    const siteUrl = encodeURIComponent(SITE_URL);
    return `
        <div class="share-row">
            <a class="share-btn whatsapp" href="https://wa.me/?text=${text}%20${url}" target="_blank" rel="noopener" title="Share on WhatsApp" onclick="event.stopPropagation()">
                <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.625.846 5.059 2.284 7.034L.789 23.492l4.628-1.475A11.932 11.932 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.75c-2.17 0-4.207-.578-5.963-1.585l-.427-.254-2.746.876.88-2.688-.278-.44A9.71 9.71 0 012.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75z"/></svg>
            </a>
            <a class="share-btn linkedin" href="https://www.linkedin.com/sharing/share-offsite/?url=${url}" target="_blank" rel="noopener" title="Share on LinkedIn" onclick="event.stopPropagation()">
                <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
            </a>
            <a class="share-btn twitter" href="https://twitter.com/intent/tweet?text=${text}&url=${url}" target="_blank" rel="noopener" title="Share on X" onclick="event.stopPropagation()">
                <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
            </a>
            <button class="share-btn copy-link" onclick="event.stopPropagation(); copyLink('${SITE_URL}?job=${job.id}', this)" title="Copy link" style="position:relative;">
                <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
                <span class="tooltip">Copied!</span>
            </button>
        </div>
    `;
}

function platformShareBtnsHtml(text, url, size) {
    const s = size || 16;
    const t = encodeURIComponent(text);
    const u = encodeURIComponent(url);
    return `
        <a class="share-btn whatsapp" href="https://wa.me/?text=${t}%20${u}" target="_blank" rel="noopener" title="WhatsApp">
            <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.625.846 5.059 2.284 7.034L.789 23.492l4.628-1.475A11.932 11.932 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.75c-2.17 0-4.207-.578-5.963-1.585l-.427-.254-2.746.876.88-2.688-.278-.44A9.71 9.71 0 012.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75z"/></svg>
        </a>
        <a class="share-btn twitter" href="https://twitter.com/intent/tweet?text=${t}&url=${u}" target="_blank" rel="noopener" title="X">
            <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
        </a>
        <a class="share-btn linkedin" href="https://www.linkedin.com/sharing/share-offsite/?url=${u}" target="_blank" rel="noopener" title="LinkedIn">
            <svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
        </a>
    `;
}

function shareDropdownHtml(job) {
    const text = encodeURIComponent(shareText(job));
    const url = encodeURIComponent(shareUrl(job));
    return `
        <a class="share-dropdown-item whatsapp" href="https://wa.me/?text=${text}%20${url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.625.846 5.059 2.284 7.034L.789 23.492l4.628-1.475A11.932 11.932 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.75c-2.17 0-4.207-.578-5.963-1.585l-.427-.254-2.746.876.88-2.688-.278-.44A9.71 9.71 0 012.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75z"/></svg>
            WhatsApp
        </a>
        <a class="share-dropdown-item linkedin" href="https://www.linkedin.com/sharing/share-offsite/?url=${url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
            LinkedIn
        </a>
        <a class="share-dropdown-item twitter" href="https://twitter.com/intent/tweet?text=${text}&url=${url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
            X (Twitter)
        </a>
        <button class="share-dropdown-item copy" onclick="event.stopPropagation(); copyLink('${SITE_URL}?job=${job.id}', this)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
            <span class="copy-label">Copy Link</span>
        </button>
    `;
}

function toggleShareMenu(btn) {
    const dropdown = btn.querySelector('.share-dropdown');
    const isOpen = dropdown.classList.contains('open');
    // Close all other open dropdowns
    document.querySelectorAll('.share-dropdown.open').forEach(d => d.classList.remove('open'));
    if (!isOpen) dropdown.classList.add('open');
}

// Close share dropdowns when clicking outside
document.addEventListener('click', () => {
    document.querySelectorAll('.share-dropdown.open').forEach(d => d.classList.remove('open'));
});

async function copyLink(url, btnEl) {
    try {
        await navigator.clipboard.writeText(url);
        if (btnEl) {
            btnEl.classList.add('copied');
            const label = btnEl.querySelector('.copy-label');
            if (label) {
                const orig = label.textContent;
                label.textContent = 'Copied!';
                setTimeout(() => { label.textContent = orig; btnEl.classList.remove('copied'); }, 1800);
            } else {
                setTimeout(() => btnEl.classList.remove('copied'), 1800);
            }
        }
    } catch { /* fallback: do nothing */ }
}

// ============================================================
// UPVOTE
// ============================================================
async function upvoteJob(jobId) {
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;
    const alreadyVoted = hasVoted(jobId);
    if (alreadyVoted) {
        job.upvotes = Math.max((job.upvotes || 0) - 1, 0);
        removeVotedId(jobId);
    } else {
        job.upvotes = (job.upvotes || 0) + 1;
        saveVotedId(jobId);
    }
    renderJobs();
    updateModalUpvoteBtn(jobId);
    try {
        const r = await fetch(`${SUPABASE_URL}/rest/v1/raw_jobs?select=upvotes&id=eq.${jobId}`, { headers: supaHeaders });
        const rows = await r.json();
        const cur = rows[0]?.upvotes || 0;
        await fetch(`${SUPABASE_URL}/rest/v1/raw_jobs?id=eq.${jobId}`, {
            method: 'PATCH', headers: supaHeaders,
            body: JSON.stringify({ upvotes: alreadyVoted ? Math.max(cur - 1, 0) : cur + 1 }),
        });
    } catch (e) { console.error('Upvote failed:', e); }
}

function upvoteBtnHtml(jobId, count, extra) {
    const voted = hasVoted(jobId);
    return `
        <button class="upvote-btn ${voted ? 'voted' : ''} ${extra || ''}"
                onclick="event.stopPropagation(); upvoteJob(${jobId})"
                title="${voted ? 'Remove upvote' : 'Upvote this listing'}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="${voted ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
            <span class="upvote-count">${count || 0}</span>
        </button>`;
}

// ============================================================
// FLAG AS CLOSED
// ============================================================
async function flagJob(jobId) {
    if (hasFlagged(jobId)) return;
    saveFlaggedId(jobId);
    // Update button to show it was recorded, without hiding the listing
    document.querySelectorAll(`.flag-btn[data-job-id="${jobId}"]`).forEach(btn => {
        btn.textContent = 'Reported';
        btn.disabled = true;
        btn.classList.add('flag-reported');
    });
    try {
        await fetch(`${SUPABASE_URL}/rest/v1/rpc/increment_flag_count`, {
            method: 'POST',
            headers: { ...supaHeaders, 'Prefer': 'return=minimal' },
            body: JSON.stringify({ job_id: jobId }),
        });
    } catch (e) { console.error('Flag failed:', e); }
}

function flagBtnHtml(jobId) {
    const reported = hasFlagged(jobId);
    return `<button class="flag-btn ${reported ? 'flag-reported' : ''}" data-job-id="${jobId}" onclick="event.stopPropagation(); flagJob(${jobId})" title="Mark this listing as closed" ${reported ? 'disabled' : ''}>${reported ? 'Reported' : 'Closed?'}</button>`;
}

function toggleShowStale() {
    showStale = !showStale;
    applyFilters();
}

function updateModalUpvoteBtn(jobId) {
    const a = document.getElementById('modalFooter');
    if (!a) return;
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;
    const btn = a.querySelector('.upvote-btn');
    if (btn) {
        if (hasVoted(jobId)) btn.classList.add('voted'); else btn.classList.remove('voted');
        btn.querySelector('.upvote-count').textContent = job.upvotes || 0;
    }
}

// ============================================================
// INIT
// ============================================================
async function init() {
    try {
        allJobs = await fetchJobs();
        populateLocationFilter();
        updateStats();
        applyFilters();
        initScrollAnimations();
        initDisclaimer();
        renderWeeklyStats();
        renderHotJobs();
        updateCollectionBar();
        // Auto-open job modal if ?job=ID is in the URL (e.g. from shared WhatsApp links)
        const jobParam = new URLSearchParams(window.location.search).get('job');
        if (jobParam) {
            const jobId = parseInt(jobParam, 10);
            if (!isNaN(jobId)) openModal(jobId);
        }
    } catch (err) {
        console.error('Failed to load jobs:', err);
        jobsGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:48px 24px;">
            <p style="font-size:1rem;font-weight:600;margin-bottom:8px;">Unable to load jobs</p>
            <p style="color:var(--text-muted);font-size:0.85rem;margin-bottom:12px;">${err.message || 'Unknown error'}</p>
            <button onclick="location.reload()" class="btn btn-secondary" style="font-size:0.85rem;">Try again</button>
        </div>`;
    }
}

// ============================================================
// DISCLAIMER
// ============================================================
function initDisclaimer() {
    if (localStorage.getItem('dracohub-disclaimer-dismissed')) {
        disclaimer.classList.add('hidden');
    }
}

// ============================================================
// STATS
// ============================================================
function updateStats() {
    statJobs.textContent = allJobs.length;
    const companies = new Set(allJobs.map(j => j.company).filter(Boolean));
    statCompanies.textContent = companies.size;
}

// ============================================================
// WEEKLY STATS BANNER (Feature #3)
// ============================================================
function renderWeeklyStats() {
    const weekAgo = new Date(); weekAgo.setDate(weekAgo.getDate() - 7);
    const thisWeek = allJobs.filter(j => new Date(j.created_at) >= weekAgo);
    if (thisWeek.length === 0) return;

    const companies = new Set(thisWeek.map(j => j.company).filter(Boolean));
    const el = document.getElementById('weeklyStats');
    const textEl = document.getElementById('weeklyStatsText');
    const shareBtns = document.getElementById('weeklyShareBtns');

    textEl.innerHTML = `<strong>${thisWeek.length}</strong> new O&G jobs added this week from <strong>${companies.size}</strong> companies`;
    const shareMsg = `${thisWeek.length} new oil & gas jobs in Nigeria this week on DracoHub Careers`;
    shareBtns.innerHTML = platformShareBtnsHtml(shareMsg, SITE_URL, 14);
    el.style.display = 'flex';
}

// ============================================================
// HOT JOBS CARD (Feature #6)
// ============================================================
function renderHotJobs() {
    const topJobs = [...allJobs]
        .filter(j => (j.upvotes || 0) > 0)
        .sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0))
        .slice(0, 5);

    if (topJobs.length < 2) return; // only show if we have enough upvoted jobs

    const card = document.getElementById('hotJobsCard');
    const list = document.getElementById('hotJobsList');
    const share = document.getElementById('hotJobsShare');

    list.innerHTML = topJobs.map((job, i) => `
        <li onclick="openModal(${job.id})" style="cursor:pointer;">
            <span class="hot-job-rank">${i + 1}</span>
            <div class="hot-job-info">
                <div class="hot-job-info-title">${escapeHtml(job.job_title)}</div>
                <div class="hot-job-info-company">${escapeHtml(job.company || 'Company not listed')}</div>
            </div>
            <span class="hot-job-votes">${job.upvotes} votes</span>
        </li>
    `).join('');

    const shareMsg = `Top upvoted O&G jobs this week on DracoHub Careers`;
    share.innerHTML = `<span class="share-label">Share this list</span>${platformShareBtnsHtml(shareMsg, SITE_URL, 14)}`;
    card.style.display = 'block';
}

// ============================================================
// LOCATION FILTER
// ============================================================
function populateLocationFilter() {
    const locations = new Set();
    allJobs.forEach(job => {
        if (job.location) {
            const parts = job.location.split(',').map(s => s.trim());
            locations.add(parts[0]);
        }
    });
    [...locations].sort().forEach(loc => {
        const opt = document.createElement('option');
        opt.value = loc; opt.textContent = loc;
        filterLocation.appendChild(opt);
    });
}

// ============================================================
// FILTER & RENDER
// ============================================================
function applyFilters() {
    const query = searchInput.value.toLowerCase().trim();
    const source = filterSource ? filterSource.value : '';
    const category = filterCategory ? filterCategory.value : '';
    const seniority = filterSeniority ? filterSeniority.value : '';
    const employment = filterEmployment ? filterEmployment.value : '';
    const location = filterLocation.value.toLowerCase();
    const sort = filterSort.value;
    const thirtyDaysAgo = new Date(); thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    // First pass: apply all filters except date
    const candidates = allJobs.filter(job => {
        if ((job.flag_count || 0) >= 3) return false;
        if (query) {
            const s = `${job.job_title} ${job.company} ${job.location} ${job.description}`.toLowerCase();
            if (!s.includes(query)) return false;
        }
        if (source && job.source !== source) return false;
        if (category && job.tags?.category !== category) return false;
        if (seniority && job.tags?.seniority !== seniority) return false;
        if (employment && job.tags?.employment_type !== employment) return false;
        if (location && !(job.location || '').toLowerCase().includes(location)) return false;
        return true;
    });

    // Count how many would be hidden by the 30-day filter
    staleCount = candidates.filter(j => new Date(j.created_at) < thirtyDaysAgo).length;

    // Second pass: apply date filter unless user opted in
    filteredJobs = showStale ? candidates : candidates.filter(j => new Date(j.created_at) >= thirtyDaysAgo);

    if (sort === 'newest') filteredJobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    else if (sort === 'oldest') filteredJobs.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    else if (sort === 'upvotes') filteredJobs.sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0));
    else if (sort === 'company') filteredJobs.sort((a, b) => (a.company || '').localeCompare(b.company || ''));

    displayCount = PAGE_SIZE;
    renderJobs();
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

    // Stale notice
    let staleNotice = document.getElementById('staleNotice');
    if (!staleNotice) {
        staleNotice = document.createElement('p');
        staleNotice.id = 'staleNotice';
        staleNotice.className = 'stale-notice';
        resultsCount.parentNode.insertBefore(staleNotice, resultsCount.nextSibling);
    }
    if (staleCount > 0 && !showStale) {
        staleNotice.innerHTML = `${staleCount} older listing${staleCount !== 1 ? 's' : ''} hidden (30+ days) · <button class="stale-toggle" onclick="toggleShowStale()">Show all</button>`;
    } else if (showStale && staleCount > 0) {
        staleNotice.innerHTML = `Showing all listings including older ones · <button class="stale-toggle" onclick="toggleShowStale()">Hide older</button>`;
    } else {
        staleNotice.innerHTML = '';
    }

    jobsGrid.innerHTML = visible.map((job, i) => `
        <div class="job-card fade-in" onclick="openModal(${job.id})" style="animation-delay:${Math.min(i * 0.05, 0.3)}s">
            <div class="job-card-top">
                <span class="job-card-source">${escapeHtml(job.source)}</span>
                <div class="share-trigger" onclick="event.stopPropagation(); toggleShareMenu(this)" title="Share this job" role="button" tabindex="0" aria-label="Share">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                    <div class="share-dropdown" onclick="event.stopPropagation()">
                        <span class="share-dropdown-label">Share via</span>
                        ${shareDropdownHtml(job)}
                    </div>
                </div>
            </div>
            <h3 class="job-card-title">${escapeHtml(job.job_title)}</h3>
            <p class="job-card-company">${escapeHtml(job.company || 'Company not listed')}</p>
            <div class="job-card-meta">
                ${job.location ? `<span>${escapeHtml(job.location)}</span>` : ''}
                ${job.date_posted ? `<span>${formatDate(job.date_posted)}</span>` : ''}
            </div>
            ${job.tags ? `<div class="job-tags">
                ${job.tags.category ? `<span class="job-tag tag-category">${escapeHtml(job.tags.category)}</span>` : ''}
                ${job.tags.discipline ? `<span class="job-tag tag-discipline">${escapeHtml(job.tags.discipline)}</span>` : ''}
                ${job.tags.seniority && job.tags.seniority !== 'Mid-Level' ? `<span class="job-tag tag-seniority">${escapeHtml(job.tags.seniority)}</span>` : ''}
                ${job.tags.employment_type && job.tags.employment_type !== 'Full-time' ? `<span class="job-tag tag-employment">${escapeHtml(job.tags.employment_type)}</span>` : ''}
            </div>` : ''}
            <p class="job-card-desc">${escapeHtml(truncate(job.description, 160))}</p>
            <div class="job-card-actions">
                <div style="display:flex;gap:6px;align-items:center;">
                    ${upvoteBtnHtml(job.id, job.upvotes)}
                    <button class="save-btn ${isSaved(job.id) ? 'saved' : ''}" onclick="event.stopPropagation(); toggleSaved(${job.id})" title="${isSaved(job.id) ? 'Remove from collection' : 'Save to collection'}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="${isSaved(job.id) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg>
                    </button>
                </div>
                <div class="job-card-buttons">
                    ${flagBtnHtml(job.id)}
                    ${job.apply_url ? `<a href="${escapeHtml(job.apply_url)}" target="_blank" rel="noopener" class="btn btn-primary" onclick="event.stopPropagation()">Apply</a>` : ''}
                </div>
            </div>
        </div>
    `).join('');

    requestAnimationFrame(() => {
        document.querySelectorAll('.job-card.fade-in').forEach(el => el.classList.add('visible'));
    });
    loadMoreWrap.style.display = displayCount < filteredJobs.length ? 'block' : 'none';
}

// ============================================================
// MODAL
// ============================================================
function openModal(jobId) {
    const job = allJobs.find(j => j.id === jobId);
    if (!job) return;

    // Track views for nudge
    modalViewCount++;
    checkShareNudge();

    // ── Header
    const avatarEl = document.getElementById('modalAvatar');
    const sourceEl = document.getElementById('modalSource');
    if (avatarEl) avatarEl.textContent = (job.company || job.source || '?').charAt(0);
    if (sourceEl) sourceEl.textContent = job.source || '';

    // ── Meta pills
    const metaPills = [];
    if (job.location) metaPills.push(`<span class="modal-meta-pill">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
        ${escapeHtml(job.location)}</span>`);
    if (job.date_posted) metaPills.push(`<span class="modal-meta-pill">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        ${formatDate(job.date_posted)}</span>`);
    if (job.tags) {
        if (job.tags.seniority) metaPills.push(`<span class="modal-meta-pill">${escapeHtml(job.tags.seniority)}</span>`);
        if (job.tags.employment_type) metaPills.push(`<span class="modal-meta-pill">${escapeHtml(job.tags.employment_type)}</span>`);
    }

    // ── Tag chips
    let tagsHtml = '';
    if (job.tags) {
        const chips = [];
        if (job.tags.category)   chips.push(`<span class="job-tag tag-category">${escapeHtml(job.tags.category)}</span>`);
        if (job.tags.discipline) chips.push(`<span class="job-tag tag-discipline">${escapeHtml(job.tags.discipline)}</span>`);
        (job.tags.skills || []).slice(0, 5).forEach(s => chips.push(`<span class="job-tag tag-skill">${escapeHtml(s)}</span>`));
        if (chips.length) tagsHtml = `<div class="modal-tags">${chips.join('')}</div>`;
    }

    // ── Body
    modalBody.innerHTML = `
        <h2 class="modal-title">${escapeHtml(job.job_title)}</h2>
        <p class="modal-company">${escapeHtml(job.company || 'Company not listed')}</p>
        ${metaPills.length ? `<div class="modal-meta">${metaPills.join('')}</div>` : ''}
        ${tagsHtml}
        ${job.description ? `
        <div class="modal-divider"></div>
        <div class="modal-section-label">Job Description</div>
        <div class="modal-desc">${escapeHtml(job.description)}</div>` : ''}
        <div class="modal-share" style="margin-top:24px;">
            <span class="share-label">Share</span>
            ${shareBtnsHtml(job, 16)}
        </div>
    `;

    // ── Sticky footer actions
    const footerEl = document.getElementById('modalFooter');
    if (footerEl) {
        footerEl.innerHTML = `
            ${upvoteBtnHtml(job.id, job.upvotes)}
            <button class="save-btn ${isSaved(job.id) ? 'saved' : ''}" onclick="toggleSaved(${job.id})" title="${isSaved(job.id) ? 'Remove from collection' : 'Save to collection'}" style="width:42px;height:42px;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="${isSaved(job.id) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg>
            </button>
            ${flagBtnHtml(job.id)}
            ${job.apply_url ? `<a href="${escapeHtml(job.apply_url)}" target="_blank" rel="noopener" class="btn btn-primary modal-apply">Apply Now →</a>` : ''}
        `;
    }

    // Update URL so job can be linked/shared
    const url = new URL(window.location.href);
    url.searchParams.set('job', job.id);
    history.replaceState(null, '', url.toString());

    modalBody.scrollTop = 0;
    modalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    const panel = document.getElementById('jobModal');
    if (panel) {
        panel.classList.add('closing');
        setTimeout(() => {
            panel.classList.remove('closing');
            modalOverlay.classList.remove('open');
        }, 220);
    } else {
        modalOverlay.classList.remove('open');
    }
    document.body.style.overflow = '';
    // Remove ?job= from URL
    const url = new URL(window.location.href);
    url.searchParams.delete('job');
    history.replaceState(null, '', url.toString());
}

// ============================================================
// SHARE NUDGE (Feature #2 — appears after 3 job views)
// ============================================================
function checkShareNudge() {
    if (modalViewCount === 3 && !localStorage.getItem('dracohub-nudge-dismissed')) {
        setTimeout(() => shareNudge.classList.add('visible'), 500);
        // Set up the nudge WhatsApp link
        const nudgeMsg = encodeURIComponent(`Check out DracoHub Careers — they aggregate oil & gas jobs across Nigeria from LinkedIn, Indeed, Jobberman and more: ${SITE_URL}`);
        document.getElementById('nudgeWhatsApp').href = `https://wa.me/?text=${nudgeMsg}`;
    }
}

// ============================================================
// SAVE & SHARE COLLECTION (Feature #5)
// ============================================================
function updateCollectionBar() {
    const saved = getSavedIds();
    collectionCount.textContent = saved.size;
    if (saved.size > 0) {
        collectionBar.classList.add('visible');
    } else {
        collectionBar.classList.remove('visible');
    }
}

function shareCollection() {
    const saved = getSavedIds();
    const jobs = allJobs.filter(j => saved.has(j.id));
    if (jobs.length === 0) return;

    const lines = jobs.map((j, i) => `${i + 1}. ${j.job_title}${j.company ? ' at ' + j.company : ''}${j.location ? ' (' + j.location + ')' : ''}`);
    const text = `Check out these ${jobs.length} O&G jobs I found on DracoHub Careers:\n\n${lines.join('\n')}\n\nBrowse more: ${SITE_URL}`;
    const encoded = encodeURIComponent(text);

    // Open WhatsApp share (most common sharing path in Nigeria)
    window.open(`https://wa.me/?text=${encoded}`, '_blank');
}

function clearCollection() {
    localStorage.removeItem('dracohub-saved');
    updateCollectionBar();
    renderJobs();
}

// ============================================================
// AUTH — NAV STATE (index.html only, non-blocking)
// Supabase CDN is injected dynamically so it NEVER blocks jobs.
// ============================================================
let sb = null;

function updateNavAuth(session) {
    const navAuth = document.getElementById('navAuth');
    const mobileNavAuth = document.getElementById('mobileNavAuth');
    const navLoginLink = document.getElementById('navLoginLink');
    if (!navAuth) return;

    if (!session) {
        navAuth.innerHTML = '';
        if (navLoginLink) navLoginLink.style.display = '';
        if (mobileNavAuth) {
            mobileNavAuth.innerHTML = `<a href="login.html" class="mobile-menu-link" style="color:var(--accent);font-weight:600;">Log In / My Profile</a>`;
        }
        return;
    }

    // Logged in — hide static Log In link, show avatar dropdown instead
    if (navLoginLink) navLoginLink.style.display = 'none';
    const user = session.user;
    const name = user.user_metadata?.name || user.email || '';
    const initials = name
        ? name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
        : user.email[0].toUpperCase();

    navAuth.innerHTML = `
        <div class="nav-user-wrap" id="navUserWrap">
            <button class="nav-user-btn" id="navUserBtn" aria-label="Account menu">
                <span class="nav-user-avatar">${initials}</span>
            </button>
            <div class="nav-user-dropdown" id="navUserDropdown">
                <div class="nav-user-info">
                    <strong>${escapeHtml(name.split(' ')[0] || user.email)}</strong>
                    <span>${escapeHtml(user.email)}</span>
                </div>
                <div class="nav-user-divider"></div>
                <a href="profile.html" class="nav-user-item">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    My Profile
                </a>
                <button class="nav-user-item nav-user-signout" onclick="navSignOut()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    Sign Out
                </button>
            </div>
        </div>`;

    if (mobileNavAuth) {
        mobileNavAuth.innerHTML = `<a href="profile.html" class="mobile-menu-link" style="color:var(--accent);font-weight:600;">My Profile</a>`;
    }

    document.getElementById('navUserBtn').addEventListener('click', e => {
        e.stopPropagation();
        document.getElementById('navUserDropdown').classList.toggle('open');
    });
    document.addEventListener('click', () => {
        const dd = document.getElementById('navUserDropdown');
        if (dd) dd.classList.remove('open');
    }, { once: false });
}

async function navSignOut() {
    if (sb) await sb.auth.signOut();
    updateNavAuth(null);
}

function tryInitSupabase() {
    if (sb) return true;
    if (!window.supabase) return false;
    try {
        sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
        return true;
    } catch(e) {
        console.warn('Supabase createClient failed:', e);
        return false;
    }
}

function initNavAuth() {
    if (!tryInitSupabase()) {
        // CDN not ready yet — retry once after 1 second
        setTimeout(function() {
            if (tryInitSupabase()) {
                wireSupabaseListeners();
            } else {
                console.warn('Supabase CDN still not available after retry — nav auth disabled');
            }
        }, 1000);
        return;
    }
    wireSupabaseListeners();
}

function wireSupabaseListeners() {
    sb.auth.getSession().then(function(result) {
        const session = result?.data?.session || null;
        updateNavAuth(session);
        initSubscribeSection();
    }).catch(function() {
        updateNavAuth(null);
        initSubscribeSection();
    });
    sb.auth.onAuthStateChange(function(_event, session) {
        updateNavAuth(session);
        initSubscribeSection();
    });
}

// ============================================================
// DARK MODE
// ============================================================
function initTheme() {
    const stored = localStorage.getItem('dracohub-theme');
    // Default is light; only switch if user has explicitly toggled before
    if (stored) document.documentElement.setAttribute('data-theme', stored);
}

function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('dracohub-theme', next);
}

// ============================================================
// MOBILE MENU & SCROLL ANIMATIONS
// ============================================================
function toggleMobileMenu() { mobileMenu.classList.toggle('open'); }

function initScrollAnimations() {
    const obs = new IntersectionObserver(entries => {
        entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
    }, { threshold: 0.1 });
    document.querySelectorAll('.feature-card, .about-text, .subscribe-card, .hot-jobs-card').forEach(el => {
        el.classList.add('fade-in'); obs.observe(el);
    });
}

// ============================================================
// HELPERS
// ============================================================
function escapeHtml(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function truncate(s, n) { if (!s) return ''; return s.length > n ? s.slice(0, n) + '...' : s; }
function formatDate(s) {
    if (!s) return '';
    try {
        // Handle relative strings from scrapers (e.g. "3 days ago", "2 weeks ago")
        if (/ago|today|yesterday/i.test(s)) return s;
        const d = new Date(s);
        if (isNaN(d.getTime())) return s;
        // Reject implausible years (partial dates like "11 March" parse as year 11)
        if (d.getFullYear() < 2020) return s;
        return d.toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch { return s; }
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ============================================================
// EVENT LISTENERS
// ============================================================
searchInput.addEventListener('input', debounce(applyFilters, 300));
filterSource && filterSource.addEventListener('change', applyFilters);
filterCategory && filterCategory.addEventListener('change', applyFilters);
filterSeniority && filterSeniority.addEventListener('change', applyFilters);
filterEmployment && filterEmployment.addEventListener('change', applyFilters);
filterLocation.addEventListener('change', applyFilters);
filterSort.addEventListener('change', applyFilters);
loadMoreBtn.addEventListener('click', () => { displayCount += PAGE_SIZE; renderJobs(); });
modalClose.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
themeToggle.addEventListener('click', toggleTheme);
mobileMenuBtn.addEventListener('click', toggleMobileMenu);
disclaimerClose.addEventListener('click', () => {
    disclaimer.classList.add('hidden');
    localStorage.setItem('dracohub-disclaimer-dismissed', '1');
});
shareNudgeClose.addEventListener('click', () => {
    shareNudge.classList.remove('visible');
    localStorage.setItem('dracohub-nudge-dismissed', '1');
});
document.getElementById('nudgeCopyLink').addEventListener('click', () => {
    copyLink(SITE_URL);
    shareNudge.classList.remove('visible');
    localStorage.setItem('dracohub-nudge-dismissed', '1');
});
document.getElementById('shareCollection').addEventListener('click', shareCollection);
document.getElementById('clearCollection').addEventListener('click', clearCollection);
document.querySelectorAll('.mobile-menu-link').forEach(l => l.addEventListener('click', () => mobileMenu.classList.remove('open')));

// ============================================================
// DIGEST FORM REFS
// ============================================================
const alertForm    = document.getElementById('alertForm');
const alertSuccess = document.getElementById('alertSuccess');

// Prevent accidental form submission
if (alertForm) alertForm.addEventListener('submit', e => e.preventDefault());

// Wire up the subscribe button — the <a> tag works as a plain link with no JS,
// but when JS loads we intercept the click to handle payment logic properly.
const digestBtnEl = document.getElementById('digestBtn');
if (digestBtnEl) {
    digestBtnEl.addEventListener('click', function(e) {
        e.preventDefault();
        startDigestPayment();
    });
}

// ============================================================
// SUBSCRIBE SECTION — auth-gated Flutterwave payment
// ============================================================

// Check auth state and update subscribe section accordingly.
// The form is ALWAYS visible — auth state only changes the identity bar
// and the button label, so there's never a "hidden" Subscribe button.
async function initSubscribeSection() {
    const userBarEl = document.getElementById('alertUserBar');
    const btnText   = document.getElementById('digestBtnText');
    const note      = document.getElementById('subscribeNote');

    if (!userBarEl) return; // not on index page

    let session = null;
    try {
        const { data } = await sb.auth.getSession();
        session = data.session;
    } catch(e) { /* non-fatal */ }

    if (!session) {
        // Logged out — hide identity bar, update button to explain login step
        userBarEl.style.display = 'none';
        if (btnText) btnText.textContent = 'Create Account & Subscribe →';
        if (note)    note.textContent    = 'Free account required · takes 30 seconds · Secure payment via Flutterwave';
    } else {
        // Logged in — show identity bar, restore button to payment label
        const user     = session.user;
        const name     = user.user_metadata?.full_name || user.user_metadata?.name || '';
        const email    = user.email || '';
        const initials = name
            ? name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
            : email[0].toUpperCase();

        const avatarEl = document.getElementById('alertUserAvatar');
        const nameEl   = document.getElementById('alertUserName');
        const emailEl  = document.getElementById('alertUserEmail');
        if (avatarEl) avatarEl.textContent = initials;
        if (nameEl)   nameEl.textContent   = name || email;
        if (emailEl)  emailEl.textContent  = name ? email : '';
        userBarEl.style.display = 'flex';
        if (btnText) btnText.textContent = 'Subscribe — ₦3,000/mo';
        if (note)    note.textContent    = 'Billed monthly · Cancel anytime · Secure payment via Flutterwave';

        // Restore any form state saved before the login redirect
        const saved = localStorage.getItem('dh_subscribe_draft');
        if (saved) {
            try {
                const draft = JSON.parse(saved);
                const cat = document.getElementById('alertCategory');
                const sen = document.getElementById('alertSeniority');
                const loc = document.getElementById('alertLocation');
                const bg  = document.getElementById('alertBackground');
                if (cat && draft.category)   cat.value = draft.category;
                if (sen && draft.seniority)  sen.value = draft.seniority;
                if (loc && draft.location)   loc.value = draft.location;
                if (bg  && draft.background) bg.value  = draft.background;
            } catch(e) {}
            localStorage.removeItem('dh_subscribe_draft');

            // User just came back from login — auto-open checkout after a short
            // delay so Flutterwave CDN has time to finish loading
            setTimeout(function() {
                startDigestPayment();
            }, 800);
        }
    }
}

// Save form state then redirect to login
function goLoginToSubscribe() {
    const draft = {
        category:   document.getElementById('alertCategory')?.value   || '',
        seniority:  document.getElementById('alertSeniority')?.value  || '',
        location:   document.getElementById('alertLocation')?.value   || '',
        background: document.getElementById('alertBackground')?.value || '',
    };
    localStorage.setItem('dh_subscribe_draft', JSON.stringify(draft));
    window.location.href = 'login.html?next=' + encodeURIComponent('index.html#subscribe');
}

async function startDigestPayment() {
  try {
    // Try to init Supabase now if it wasn't ready at page load (CDN slowness)
    if (!sb) tryInitSupabase();

    // If Supabase is still unavailable (CDN completely failed), show a message
    // and DO NOT redirect — that would cause a bounce loop for logged-in users
    if (!sb) {
        alert('Auth service still loading — please wait a moment and try again.');
        return;
    }

    // Try to get session
    let session = null;
    try {
        const { data } = await sb.auth.getSession();
        session = data?.session || null;
    } catch(e) { /* fall through to login redirect */ }

    if (!session) { goLoginToSubscribe(); return; }

    // Guard: Flutterwave must be loaded
    if (typeof FlutterwaveCheckout === 'undefined') {
        alert('Payment system is still loading. Please wait a moment and try again.');
        return;
    }

    const user          = session.user;
    const email         = user.email;
    const name          = user.user_metadata?.full_name || user.user_metadata?.name || '';
    const category      = document.getElementById('alertCategory').value;
    const seniority     = document.getElementById('alertSeniority').value;
    const location_pref = document.getElementById('alertLocation').value;
    const background    = document.getElementById('alertBackground').value;

    const btn = document.getElementById('digestBtn');
    document.getElementById('digestBtnText').style.display    = 'none';
    document.getElementById('digestBtnSpinner').style.display = 'inline';
    if (btn) btn.style.pointerEvents = 'none'; // prevent double-click (a tag, not button)

    const tx_ref = 'DH-' + Date.now();

    FlutterwaveCheckout({
        public_key:      FLW_PUBLIC_KEY,
        tx_ref,
        amount:          3000,
        currency:        'NGN',
        payment_options: 'card, banktransfer, ussd',
        customer: { email, name },
        meta: { category, seniority, location_pref, background },
        customizations: {
            title:       'DracoHub Weekly Digest',
            description: 'Monthly subscription — ₦3,000/month',
            logo:        'https://dracohub.co/favicon.png',
        },
        callback: async function(response) {
            if (response.status === 'successful' || response.status === 'completed') {
                await handleDigestSuccess(
                    { email, name, user_id: user.id, category, seniority, location_pref, background },
                    response.tx_ref,
                    response.transaction_id
                );
            } else {
                document.getElementById('digestBtnText').style.display    = 'inline';
                document.getElementById('digestBtnSpinner').style.display = 'none';
                if (btn) btn.style.pointerEvents = '';
            }
        },
        onclose: function() {
            document.getElementById('digestBtnText').style.display    = 'inline';
            document.getElementById('digestBtnSpinner').style.display = 'none';
            if (btn) btn.style.pointerEvents = '';
        },
    });
  } catch(err) {
      alert('Error: ' + err.message);
      console.error('startDigestPayment error:', err);
  }
}

async function handleDigestSuccess(profile, flw_ref, flw_tx_id) {
    try {
        const expiresAt = new Date();
        expiresAt.setDate(expiresAt.getDate() + 30);

        const { error } = await sb
            .from('subscribers')
            .upsert({
                user_id:                profile.user_id,
                email:                  profile.email,
                name:                   profile.name        || null,
                category:               profile.category    || null,
                seniority:              profile.seniority   || null,
                location_pref:          profile.location_pref || null,
                background:             profile.background  || null,
                subscription_status:    'paid',
                flw_ref:                flw_ref,
                flw_tx_id:              String(flw_tx_id),
                subscription_expires_at: expiresAt.toISOString(),
            }, { onConflict: 'user_id', ignoreDuplicates: false });

        if (error) console.error('Subscriber upsert failed:', error.message);
    } catch (e) {
        console.error('Failed to save subscription:', e);
    }

    // Show success + redirect to profile
    alertForm.style.display    = 'none';
    document.getElementById('alertUserBar').style.display = 'none';
    alertSuccess.style.display = 'flex';

    let secs = 5;
    const countdown = document.getElementById('redirectCountdown');
    if (countdown) countdown.textContent = `Redirecting in ${secs}s…`;
    const timer = setInterval(() => {
        secs--;
        if (countdown) countdown.textContent = secs > 0 ? `Redirecting in ${secs}s…` : '';
        if (secs <= 0) {
            clearInterval(timer);
            window.location.href = 'profile.html?welcome=1';
        }
    }, 1000);
}

// Scroll to subscribe section if redirected back after login
if (window.location.hash === '#subscribe') {
    setTimeout(() => {
        const el = document.querySelector('.subscribe-card');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 400);
}

// initSubscribeSection() is called from initNavAuth() once Supabase client is ready

// ============================================================
// BOOT
// ============================================================
initTheme();
init();        // jobs load immediately — never waits for auth
initNavAuth(); // updates nav asynchronously after jobs are loading
