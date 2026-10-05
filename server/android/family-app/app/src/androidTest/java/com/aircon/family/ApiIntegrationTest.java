package com.aircon.family;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.*;
import java.io.*;
import static org.junit.Assert.*;
@RunWith(AndroidJUnit4.class)
public class ApiIntegrationTest {
    @Test public void realAndroidTransportEnforcesHouseholdAuthority() throws Exception {
        JSONObject fixture;
        try(InputStream input=InstrumentationRegistry.getInstrumentation().getTargetContext().getAssets().open("test-fixture.json")){
            ByteArrayOutputStream output=new ByteArrayOutputStream();byte[] buffer=new byte[4096];int count;
            while((count=input.read(buffer))!=-1) output.write(buffer,0,count);
            fixture=new JSONObject(output.toString("UTF-8"));
        }
        ApiClient api=new ApiClient("http://127.0.0.1:8765",true);
        String owner=fixture.getString("owner_token"),other=fixture.getString("other_token"),family=fixture.getString("family_token"),guest=fixture.getString("guest_token");
        JSONArray homes=api.request(owner,"GET","/v1/me",null).getJSONArray("homes");
        String home=null;
        for(int index=0;index<homes.length();index++) if(homes.getJSONObject(index).getString("name").equals("시험용 우리 집")) home=homes.getJSONObject(index).getString("id");
        assertNotNull(home);String base="/v1/homes/"+home;
        denied(api,other,"GET",base,null,404);
        denied(api,family,"GET",base+"/members",null,403);
        String member=api.request(family,"GET","/v1/me",null).getString("user_id");
        api.request(owner,"PATCH",base+"/members/"+member,new JSONObject().put("role","viewer"));
        assertEquals("viewer",api.request(family,"GET",base,null).getString("role"));
        JSONObject invitation=api.request(owner,"POST",base+"/invitations",new JSONObject().put("email","guest@example.test").put("role","viewer"));
        JSONObject claim=new JSONObject().put("invitation_token",invitation.getString("invitation_token"));
        denied(api,other,"POST","/v1/invitations/accept",claim,404);
        api.request(guest,"POST","/v1/invitations/accept",claim);
        denied(api,guest,"POST","/v1/invitations/accept",claim,404);
        api.request(owner,"POST",base+"/members/"+member+"/revoke",new JSONObject());
        denied(api,family,"GET",base+"/events",null,404);
        denied(api,owner,"GET","/v1/redirect",null,307);
        denied(api,"forged-token","GET","/v1/me",null,401);
    }
    private void denied(ApiClient api,String token,String method,String path,JSONObject body,int status) throws Exception {
        try { api.request(token,method,path,body); fail("Unauthorized request succeeded"); }
        catch(ApiClient.Failure failure){ assertEquals(status,failure.status); }
    }
}
