// Vercel serverless function — Flutterwave webhook handler
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
        return res.status(200).json({ received: true, action: 'activated', email });

    } catch (err) {
        console.error('Supabase error:', err);
        return res.status(500).json({ error: 'Database error' });
    }
}
