package com.aircon.family;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public final class ApiClient {
    public static final class Failure extends Exception {
        public final int status;
        public final String code;
        public Failure(int status, String code) { super(code); this.status=status; this.code=code; }
    }
    private final String origin;
    public ApiClient(String origin, boolean debug) { this.origin=EndpointPolicy.validate(origin, debug); }
    public JSONObject request(String token, String method, String path, JSONObject body) throws Exception {
        if (!path.startsWith("/v1/") || path.contains("..") || path.contains("?") || path.contains("#"))
            throw new IllegalArgumentException("Invalid API path");
        HttpURLConnection connection=(HttpURLConnection) URI.create(origin+path).toURL().openConnection();
        try {
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(8000); connection.setReadTimeout(8000);
            connection.setRequestMethod(method);
            connection.setRequestProperty("Authorization", "Bearer "+token);
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
            JSONObject value;
            try { value=new JSONObject(bytes.toString("UTF-8")); }
            catch (Exception error) { throw new Failure(status,"invalid_response"); }
            if (status>=400) throw new Failure(status,value.optString("error","request_failed"));
            return value;
        } finally { connection.disconnect(); }
    }
}
