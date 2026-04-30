// Vercel serverless function — Flutterwave webhook handler
// Also sends a welcome email with a job snapshot immediately after payment
//
// Additional env var needed:
//   RESEND_API_KEY  — for sending the welcome email
//   DIGEST_FROM_EMAIL — e.g. "DracoHub <digest@dracohub.co>"
// URL: https://dracohub.co/api/flutterwave
//
// Required environment variables (set in Vercel dashboard):
//   FLW_WEBHOOK_SECRET   — the secret hash set in Flutterwave > Settings > Webhooks
//   FLW_SECRET_KEY       — Flutterwave secret key (FLWSECK_...)
//   SUPABASE_URL         — Supabase project URL
//   SUPABASE_SERVICE_KEY — Supabase service role key (bypasses RLS)

export default async function handler(req, res) {
    // Only accept POST
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    // ── 1. Verify webhook signature ──
    const incomingHash = req.headers['verif-hash'];
    if (!incomingHash || incomingHash !== process.env.FLW_WEBHOOK_SECRET) {
        console.error('Webhook signature mismatch');
        return res.status(401).json({ error: 'Unauthorized' });
    }

    const payload = req.body;
    console.log('Flutterwave webhook event:', payload?.event, payload?.data?.status);

    // ── 2. Only process successful charge events ──
    if (payload?.event !== 'charge.completed' || payload?.data?.status !== 'successful') {
        return res.status(200).json({ received: true, action: 'ignored' });
    }

    const { customer, tx_ref, id: flw_tx_id, amount, currency } = payload.data;
    const email = customer?.email;

    if (!email) {
        console.error('No email in webhook payload');
        return res.status(200).json({ received: true, action: 'no_email' });
    }

    // ── 3. Verify transaction with Flutterwave API (prevent replay attacks) ──
    try {
        const verifyResp = await fetch(
            `https://api.flutterwave.com/v3/transactions/${flw_tx_id}/verify`,
            {
                headers: {
                    'Authorization': `Bearer ${process.env.FLW_SECRET_KEY}`,
                    'Content-Type': 'application/json',
                },
            }
        );
        const verifyData = await verifyResp.json();

        if (
            verifyData.status !== 'success' ||
            verifyData.data?.status !== 'successful' ||
            verifyData.data?.amount < 3000 ||
            verifyData.data?.currency !== 'NGN'
        ) {
            console.error('Transaction verification failed:', verifyData);
            return res.status(200).json({ received: true, action: 'verification_failed' });
        }
    } catch (err) {
        console.error('Flutterwave verify error:', err);
        // Still proceed — don't block subscriber on network error
    }

    // ── 4. Upsert subscriber in Supabase ──
    const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

    try {
        const sbResp = await fetch(
            `${process.env.SUPABASE_URL}/rest/v1/subscribers?email=eq.${encodeURIComponent(email)}`,
            {
                method: 'PATCH',
                headers: {
                    'apikey':        process.env.SUPABASE_SERVICE_KEY,
                    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
                    'Content-Type':  'application/json',
                    'Prefer':        'return=minimal',
                },
                body: JSON.stringify({
                    subscription_status:  'paid',
                    flw_ref:              tx_ref,
                    flw_tx_id:            String(flw_tx_id),
                    subscription_expires_at: expiresAt,
                }),
            }
        );

        if (!sbResp.ok) {
            const errText = await sbResp.text();
            console.error('Supabase PATCH failed:', sbResp.status, errText);

            // If row doesn't exist yet, insert it
            if (sbResp.status === 404 || errText.includes('0 rows')) {
                await fetch(
                    `${process.env.SUPABASE_URL}/rest/v1/subscribers`,
                    {
                        method: 'POST',
                        headers: {
                            'apikey':        process.env.SUPABASE_SERVICE_KEY,
                            'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
                            'Content-Type':  'application/json',
                            'Prefer':        'return=minimal',
                        },
                        body: JSON.stringify({
                            email,
                            name:                    customer?.name || null,
                            subscription_status:     'paid',
                            flw_ref:                 tx_ref,
                            flw_tx_id:               String(flw_tx_id),
                            subscription_expires_at: expiresAt,
                            frequency:               'weekly',
                        }),
                    }
                );
            }
        }

        console.log(`✓ Subscriber activated: ${email} (tx: ${tx_ref})`);

        // ── 5. Send welcome email with job snapshot ──
        await sendWelcomeEmail(email, customer?.name, payload.data?.meta);

        return res.status(200).json({ received: true, action: 'activated', email });

    } catch (err) {
        console.error('Supabase error:', err);
        return res.status(500).json({ error: 'Database error' });
    }
}

// ── Welcome email ────────────────────────────────────────────────────────────
async function sendWelcomeEmail(email, fullName, meta) {
    if (!process.env.RESEND_API_KEY) return;

    const firstName = (fullName || '').split(' ')[0] || 'there';
    const category  = meta?.category || null;

    // Fetch up to 8 recent jobs — filter by category if we have it
    let jobsUrl = `${process.env.SUPABASE_URL}/rest/v1/raw_jobs?select=job_title,company,location,apply_url,tags&flag_count=lt.3&order=created_at.desc&limit=8`;
    if (category) jobsUrl += `&tags->>'category'=eq.${encodeURIComponent(category)}`;

    let jobs = [];
    try {
        const jResp = await fetch(jobsUrl, {
            headers: {
                'apikey':        process.env.SUPABASE_SERVICE_KEY,
                'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
            },
        });
        if (jResp.ok) jobs = await jResp.json();
    } catch (e) {
        console.error('Failed to fetch jobs for welcome email:', e);
    }

    const jobRows = jobs.slice(0, 6).map(j => `
        <tr>
            <td style="padding:12px 16px;border-bottom:1px solid #F3F4F6;">
                <div style="font-weight:700;font-size:0.9rem;color:#142A47;">${escapeHtml(j.job_title || '')}</div>
                <div style="font-size:0.8rem;color:#6B7280;margin-top:2px;">${escapeHtml(j.company || '')} · ${escapeHtml(j.location || '')}</div>
            </td>
            <td style="padding:12px 16px;border-bottom:1px solid #F3F4F6;text-align:right;white-space:nowrap;">
                <a href="${escapeHtml(j.apply_url || 'https://dracohub.co')}" style="background:#ED880D;color:#fff;text-decoration:none;padding:6px 14px;border-radius:6px;font-size:0.78rem;font-weight:700;">Apply</a>
            </td>
        </tr>`).join('');

    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#F9FAFB;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 24px rgba(20,42,71,0.08);">

  <!-- Header -->
  <tr><td style="background:#142A47;padding:28px 32px;text-align:center;">
    <div style="font-size:1.5rem;font-weight:800;color:#fff;letter-spacing:-0.3px;">Draco<span style="color:#ED880D;">Hub</span>.</div>
    <div style="color:#8AA0B8;font-size:0.82rem;margin-top:6px;">Nigeria's O&amp;G Career Intelligence Platform</div>
  </td></tr>

  <!-- Welcome -->
  <tr><td style="padding:28px 32px 8px;">
    <h1 style="font-size:1.2rem;font-weight:800;color:#142A47;margin:0 0 10px;">Welcome aboard, ${escapeHtml(firstName)}! 🎉</h1>
    <p style="color:#6B7280;font-size:0.9rem;line-height:1.6;margin:0 0 16px;">
      Your subscription is active. Every Monday morning your personalised digest will land in your inbox — curated roles matched to your experience, seniority, and location.
    </p>
    <p style="color:#6B7280;font-size:0.9rem;line-height:1.6;margin:0 0 24px;">
      In the meantime, here's a snapshot of roles${category ? ` in <strong>${escapeHtml(category)}</strong>` : ''} active right now on the board:
    </p>
  </td></tr>

  <!-- Jobs table -->
  <tr><td style="padding:0 32px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;">
      ${jobRows || '<tr><td style="padding:16px;color:#6B7280;font-size:0.85rem;">No current listings in your category — check back Monday.</td></tr>'}
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:28px 32px;text-align:center;">
    <a href="https://dracohub.co" style="background:#ED880D;color:#fff;text-decoration:none;padding:13px 32px;border-radius:8px;font-weight:700;font-size:0.95rem;display:inline-block;">Browse All Jobs →</a>
    <p style="margin:20px 0 0;font-size:0.8rem;color:#9CA3AF;">
      <a href="https://dracohub.co/profile.html" style="color:#9CA3AF;">Complete your profile</a> to get fully personalised matches every week.
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="border-top:1px solid #F3F4F6;padding:20px 32px;text-align:center;">
    <p style="font-size:0.75rem;color:#9CA3AF;margin:0;">DracoHub · dracohub.co · Nigeria's O&amp;G Career Platform</p>
  </td></tr>

</table></td></tr></table></body></html>`;

    try {
        await fetch('https://api.resend.com/emails', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${process.env.RESEND_API_KEY}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                from:    process.env.DIGEST_FROM_EMAIL || 'DracoHub <digest@dracohub.co>',
                to:      [email],
                subject: `Welcome to DracoHub, ${firstName} — here's your first job snapshot`,
                html,
            }),
        });
        console.log(`✓ Welcome email sent to ${email}`);
    } catch (e) {
        console.error('Welcome email failed:', e);
    }
}

function escapeHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
