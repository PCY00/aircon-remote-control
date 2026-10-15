package com.aircon.family;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public final class ApiClient {
    public static class Failure extends Exception {
        public final int status;
        public final String code;
        public Failure(int status, String code) { super(code); this.status=status; this.code=code; }
    }
    /** org.json recurses once per nesting level; a deeper body is rejected before it can exhaust the stack. */
    static final int MAX_DEPTH=64;
    private final Context context;
    private final String origin;
    public ApiClient(Context context, String origin, boolean debug) {
        this.context=context.getApplicationContext(); this.origin=EndpointPolicy.validate(origin, debug);
    }
    String origin() { return origin; }
    /** The origin must have proven the pinned server key in this process before an account token is attached. */
    public JSONObject request(String token, String method, String path, JSONObject body) throws Exception {
        if (!path.startsWith("/v1/") || path.contains("..") || path.contains("?") || path.contains("#"))
            throw new IllegalArgumentException("Invalid API path");
        ServerTrust.ensure(context, this);
        return exchange(token, method, path, body);
    }
    /** Unauthenticated: nothing about the account leaves the phone until the answer verifies. */
    JSONObject identity(String nonce) throws Exception { return exchange(null, "GET", ServerIdentity.PATH+"?nonce="+nonce, null); }
    private JSONObject exchange(String token, String method, String path, JSONObject body) throws Exception {
        HttpURLConnection connection=(HttpURLConnection) URI.create(origin+path).toURL().openConnection();
        try {
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(8000); connection.setReadTimeout(8000);
            connection.setRequestMethod(method);
            if (token != null) connection.setRequestProperty("Authorization", "Bearer "+token);
            connection.setRequestProperty("Accept", "application/json");
            if (body != null) {
                byte[] data=body.toString().getBytes(StandardCharsets.UTF_8);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
                connection.setFixedLengthStreamingMode(data.length);
                try (java.io.OutputStream output=connection.getOutputStream()) { output.write(data); }
            }
            int status=connection.getResponseCode();
            if (status>=300 && status<400) throw new Failure(status,"redirect_rejected");
            InputStream stream=status>=400 ? connection.getErrorStream() : connection.getInputStream();
            if (stream==null) throw new Failure(status,"invalid_response");
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try (InputStream input=stream) {
                byte[] buffer=new byte[4096]; int count;
                while ((count=input.read(buffer))!=-1) {
                    if (bytes.size()+count>65536) throw new Failure(status,"response_too_large");
                    bytes.write(buffer,0,count);
                }
            }
            String text=new String(bytes.toByteArray(),StandardCharsets.UTF_8);
            if (depth(text)>MAX_DEPTH) throw new Failure(status,"invalid_response");
            JSONObject value;
            try { value=new JSONObject(text); }
            catch (StackOverflowError|Exception error) { throw new Failure(status,"invalid_response"); }
            if (status>=400) throw new Failure(status,value.optString("error","request_failed"));
            return value;
        } finally { connection.disconnect(); }
    }
    /** Deepest bracket nesting outside string literals. */
    static int depth(String text) {
        int depth=0, deepest=0; boolean quoted=false;
        for (int i=0;i<text.length();i++) {
            char c=text.charAt(i);
            if (quoted) { if (c=='\\') i++; else if (c=='"') quoted=false; }
            else if (c=='"') quoted=true;
            else if (c=='{' || c=='[') deepest=Math.max(deepest,++depth);
            else if (c=='}' || c==']') depth--;
        }
        return deepest;
    }
}
