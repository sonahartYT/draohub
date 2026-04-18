import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const PAYSTACK_SECRET    = Deno.env.get("PAYSTACK_SECRET_KEY")!;
const KIT_API_KEY        = Deno.env.get("KIT_API_KEY")!;
const KIT_DIGEST_TAG_ID  = Deno.env.get("KIT_DIGEST_TAG_ID")!;
const SUPABASE_URL       = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

// Verify Paystack HMAC-SHA512 signature
async function verifySignature(body: string, signature: string): Promise<boolean> {
    const key = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(PAYSTACK_SECRET),
        { name: "HMAC", hash: "SHA-512" },
        false,
        ["sign"],
    );
    const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
    const hex = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, "0")).join("");
    return hex === signature;
}

async function kitAddTag(email: string, tagId: string) {
    await fetch(`https://api.kit.com/v4/tags/${tagId}/subscribers`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Kit-Api-Key": KIT_API_KEY },
        body: JSON.stringify({ email_address: email }),
    });
}

async function kitRemoveTag(email: string, tagId: string) {
    // Find subscriber ID first
    const res = await fetch(
        `https://api.kit.com/v4/subscribers?email_address=${encodeURIComponent(email)}`,
        { headers: { "X-Kit-Api-Key": KIT_API_KEY } },
    );
    const data = await res.json();
    const subscriberId = data?.subscribers?.[0]?.id;
    if (!subscriberId) return;

    await fetch(`https://api.kit.com/v4/tags/${tagId}/subscribers/${subscriberId}`, {
        method: "DELETE",
        headers: { "X-Kit-Api-Key": KIT_API_KEY },
    });
}

serve(async (req) => {
    const body = await req.text();
    const signature = req.headers.get("x-paystack-signature") || "";

    if (!(await verifySignature(body, signature))) {
        return new Response("Unauthorized", { status: 401 });
    }

    const event = JSON.parse(body);
    const email = event.data?.customer?.email;
    if (!email) return new Response("OK", { status: 200 });

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

    if (event.event === "charge.success" || event.event === "subscription.create") {
        await supabase.from("subscribers").upsert({
            email,
            subscription_status: "paid",
            paystack_subscription_code: event.data?.subscription_code ?? null,
            frequency: "weekly",
        }, { onConflict: "email" });

        await kitAddTag(email, KIT_DIGEST_TAG_ID);
    }

    if (event.event === "subscription.disable" || event.event === "subscription.not_renew") {
        await supabase.from("subscribers")
            .update({ subscription_status: "free" })
            .eq("email", email);

        await kitRemoveTag(email, KIT_DIGEST_TAG_ID);
    }

    return new Response("OK", { status: 200 });
});
