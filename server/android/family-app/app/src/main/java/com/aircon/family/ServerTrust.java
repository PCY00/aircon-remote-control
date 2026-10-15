package com.aircon.family;

import android.content.Context;
import android.content.SharedPreferences;
import java.security.SecureRandom;
import java.util.HashSet;
import java.util.Set;
import org.json.JSONObject;

/** Each origin proves once per process that it holds the pinned server key before any account token is sent there. */
final class ServerTrust {
    /** A server that verified but is not the pinned one; only an explicit re-pin by the user accepts it. */
    static final class Changed extends ApiClient.Failure {
        final String fingerprint;
        Changed(String fingerprint) { super(0,"server_identity_changed"); this.fingerprint=fingerprint; }
    }
    private static final Set<String> verified=new HashSet<>();
    private static final SecureRandom random=new SecureRandom();
    /** The pin identifies the server, not the user: logout and address changes leave it alone. */
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("server",0); }
    static String pinned(Context c) { return prefs(c).getString("fingerprint",""); }
    static synchronized void ensure(Context c,ApiClient client) throws Exception {
        if(verified.contains(client.origin())) return;
        String nonce=ServerIdentity.nonce(random), fingerprint;
        JSONObject body;
        try { body=client.identity(nonce); }
        catch(ApiClient.Failure failure) {
            if(failure.status>=500 || failure.status==429) throw failure;
            throw new ApiClient.Failure(0,"server_identity_invalid");
        }
        try {
            fingerprint=new ServerIdentity(body.optInt("version"),body.optString("algorithm"),body.optString("public_key"),
                body.optString("fingerprint"),body.optString("host"),body.optLong("issued_at"),body.optString("signature"))
                .verify(nonce,ServerIdentity.expectedHost(client.origin()),System.currentTimeMillis()/1000);
        } catch(IllegalArgumentException invalid) { throw new ApiClient.Failure(0,"server_identity_invalid"); }
        String pinned=pinned(c);
        if(pinned.isEmpty()) prefs(c).edit().putString("fingerprint",fingerprint).commit();
        else if(!pinned.equals(fingerprint)) throw new Changed(fingerprint);
        verified.add(client.origin());
    }
    /** The user accepted a different server; everything verified against the old pin must prove itself again. */
    static synchronized void repin(Context c,String fingerprint) {
        prefs(c).edit().putString("fingerprint",fingerprint).commit(); verified.clear();
    }
    /** Fixture tests start from first contact. */
    static synchronized void forget(Context c) { prefs(c).edit().remove("fingerprint").commit(); verified.clear(); }
}
