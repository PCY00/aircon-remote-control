package com.aircon.family;
import org.json.JSONObject;
import java.io.InputStream;
import java.util.function.Consumer;
/** Separate .fixture APK only. Never packaged in production APKs. */
public final class MainActivity extends FamilyActivity {
    private JSONObject fixture;
    @Override protected AuthSession createSession() {
        try(InputStream input=getAssets().open("test-fixture.json")) {
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
            byte[] buffer=new byte[4096]; int count;
            while((count=input.read(buffer))!=-1) bytes.write(buffer,0,count);
            fixture=new JSONObject(bytes.toString("UTF-8"));
        } catch(Exception error) { throw new IllegalStateException("Missing isolated test fixture"); }
        return new AuthSession() {
            private boolean active=true;
            public String userId(){ return active ? "fixture-owner" : null; }
            public String email(){ return "owner@example.test"; }
            public void token(TokenResult result){ result.done(fixture.optString("owner_token"),null); }
            public void signIn(Runnable success,Consumer<String> error){ active=true;success.run(); }
            public void signOut(){ active=false; }
        };
    }
    @Override protected String initialEndpoint(){ return "http://127.0.0.1:8765"; }
}
