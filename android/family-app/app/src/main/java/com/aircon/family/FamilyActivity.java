package com.aircon.family;

import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.WindowInsets;
import android.widget.*;
import androidx.activity.ComponentActivity;
import org.json.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/** Native family UI. Identity is obtained only through Firebase, never from Intent extras. */
public class FamilyActivity extends ComponentActivity {
    protected AuthSession session;
    private String endpoint, userId, currentHome;
    private String viewMode="login";
    private int generation=0;
    private boolean busy=false;
    private LinearLayout page;
    private final List<Button> buttons=new ArrayList<>();
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private static final int INK=Color.rgb(28,49,43), MUTED=Color.rgb(103,119,110), GREEN=Color.rgb(36,107,88);

    protected AuthSession createSession() { return new FirebaseSession(this); }
    protected String initialEndpoint() {
        return getPreferences(0).getString("endpoint",BuildConfig.DEBUG ? "http://127.0.0.1:8001" : "");
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        session=createSession(); endpoint=initialEndpoint(); loginPage();
        getOnBackPressedDispatcher().addCallback(this,new androidx.activity.OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() {
                generation++; working(false);
                if(viewMode.equals("members") && currentHome!=null) home(currentHome);
                else if(viewMode.equals("notifications")) { if(currentHome!=null) home(currentHome); else homes(); }
                else if(viewMode.equals("home")) homes();
                else moveTaskToBack(true);
            }
        });
    }
    @Override public void onResume() {
        super.onResume();
        if (session!=null && session.userId()!=null && !busy) {
            if(endpoint.isEmpty()) connectionPage(); else homes();
        }
    }
    @Override public void onDestroy() { generation++; network.shutdownNow(); super.onDestroy(); }
    private int dp(int number) { return (int)(number*getResources().getDisplayMetrics().density+.5f); }
    private GradientDrawable shape(int color, int radius) {
        GradientDrawable background=new GradientDrawable(); background.setColor(color); background.setCornerRadius(dp(radius)); return background;
    }
    private void screen(String title, String subtitle) {
        buttons.clear();
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(245,247,244));
        page=new LinearLayout(this); page.setOrientation(LinearLayout.VERTICAL); page.setPadding(dp(24),dp(24),dp(24),dp(32));
        scroll.addView(page); setContentView(scroll);
        scroll.setOnApplyWindowInsetsListener((view,insets)-> {
            view.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom()); return insets;
        });
        text(page,"우리 가족 스마트홈",12,MUTED,true);
        if(BuildConfig.FLAVOR.equals("fixture")) text(page,"동작 시험 · 가상 계정",12,Color.rgb(155,94,22),true);
        text(page,title,30,INK,true); text(page,subtitle,15,MUTED,false);
    }
    private TextView text(LinearLayout parent,String value,int size,int color,boolean bold) {
        TextView view=new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        view.setPadding(0,dp(8),0,dp(8)); view.setLineSpacing(dp(3),1); parent.addView(view); return view;
    }
    private LinearLayout card() {
        LinearLayout value=new LinearLayout(this); value.setOrientation(LinearLayout.VERTICAL); value.setPadding(dp(20),dp(16),dp(20),dp(16));
        value.setBackground(shape(Color.WHITE,20));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2); params.topMargin=dp(18); page.addView(value,params); return value;
    }
    private Button button(LinearLayout parent,String label,boolean primary,Runnable action) {
        Button view=new Button(this); view.setText(label); view.setAllCaps(false); view.setTextSize(15);
        view.setTextColor(primary ? Color.WHITE : GREEN); view.setBackground(shape(primary ? GREEN : Color.rgb(232,241,235),14));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,dp(52)); params.topMargin=dp(10); parent.addView(view,params);
        view.setEnabled(!busy); view.setOnClickListener(v -> { if (!busy) action.run(); }); buttons.add(view); return view;
    }
    private void working(boolean value) { busy=value; for (Button button:buttons) button.setEnabled(!value); }
    private void message(String value) { Toast.makeText(this,value,Toast.LENGTH_LONG).show(); }
    private static String role(String value) { return value.equals("owner") ? "소유자" : value.equals("member") ? "가족" : "조회 전용"; }
    private JSONObject json(String... fields) {
        JSONObject object=new JSONObject();
        try { for (int index=0;index<fields.length;index+=2) object.put(fields[index],fields[index+1]); }
        catch(JSONException ignored) { throw new IllegalArgumentException(); }
        return object;
    }
    private void loginPage() {
        viewMode="login";
        currentHome=null; userId=null;
        screen("우리 집을 함께", "가족만 연결되는 스마트홈");
        LinearLayout intro=card(); text(intro,"⌂",58,GREEN,true);
        text(intro,"같은 집, 각자의 계정",22,INK,true);
        text(intro,"Google 계정으로 로그인하고\n내 집을 만들거나 가족의 초대를 받아 주세요.",16,MUTED,false);
        button(intro,"Google로 계속하기",true,()-> {
            working(true); int epoch=generation;
            session.signIn(()-> { if(epoch==generation && !isDestroyed()){ working(false); if(endpoint.isEmpty()) connectionPage(); else homes(); } },error -> {
                if(epoch==generation && !isDestroyed()){ working(false); message(error); }
            });
        });
        button(page,"연결 설정",false,this::connectionSettings);
        text(page,"가족 권한은 집 소유자가 관리해요.\n다른 집의 기록은 볼 수 없어요.",13,MUTED,false);
    }
    private void connectionPage() {
        viewMode="connection";
        screen("로그인됐어요", "우리 집 서버를 연결해 주세요.");
        LinearLayout info=card();
        text(info,"우리 집 연결 주소",22,INK,true);
        text(info,"집 소유자가 안내한 주소를 입력하면 가족과 집 목록을 확인할 수 있어요.",16,MUTED,false);
        button(info,"연결 설정",true,this::connectionSettings);
        button(page,"로그아웃",false,this::logout);
    }
    private void connectionSettings() {
        EditText input=new EditText(this); input.setSingleLine(); input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(endpoint); input.setHint("https://집에서 안내받은 주소");
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("우리 집 연결 주소").setMessage("소유자가 안내한 중앙 서버 주소를 입력해 주세요.")
            .setView(input).setNegativeButton("취소",null).setPositiveButton("저장",null).create();
        dialog.setOnShowListener(unused -> dialog.getButton(-1).setOnClickListener(view -> {
            try {
                String selected=EndpointPolicy.validate(input.getText().toString(),BuildConfig.DEBUG);
                if (!endpoint.isEmpty() && !endpoint.equals(selected) && session.userId()!=null) { PushManager.disable(this); session.signOut(); }
                generation++; working(false); endpoint=selected;
                getPreferences(0).edit().putString("endpoint",endpoint).apply(); dialog.dismiss();
                if(session.userId()!=null) homes(); else loginPage();
            } catch (IllegalArgumentException error) { input.setError(error.getMessage()); }
        })); dialog.show();
    }
    private void logout() { generation++; PushManager.disable(this); session.signOut(); working(false); loginPage(); }
    private void request(String method,String path,JSONObject value,Consumer<JSONObject> success) {
        if(session.userId()==null){ logout(); return; }
        working(true); final int epoch=generation; final String account=session.userId(); final String origin=endpoint;
        session.token((token,error)-> {
            if(epoch!=generation || !account.equals(session.userId()) || isDestroyed()) return;
            if(error!=null){ working(false); message("로그인을 다시 확인해 주세요."); return; }
            network.execute(()-> {
                try {
                    JSONObject reply=new ApiClient(origin,BuildConfig.DEBUG).request(token,method,path,value);
                    runOnUiThread(()-> {
                        if(epoch!=generation || !account.equals(session.userId()) || isDestroyed()) return;
                        working(false); success.accept(reply);
                    });
                } catch(Exception failure){ runOnUiThread(()-> {
                    if(epoch!=generation || !account.equals(session.userId()) || isDestroyed()) return;
                    working(false);
                    String detail=ApiErrorMessages.describe(failure);
                    if(failure instanceof ApiClient.Failure){
                        ApiClient.Failure f=(ApiClient.Failure)failure;
                        if(f.status==409 && f.code.equals("installation_not_registered")) {
                            PushManager.sync(this);
                            notificationHelp("이 휴대폰의 알림을 연결해 주세요",detail);
                            return;
                        }
                        if((f.status==403 || f.status==404) && currentHome!=null){ currentHome=null; homes(); }
                    }
                    message(detail);
                }); }
            });
        });
    }
    private void homes() {
        viewMode="homes";
        PushManager.sync(this);
        generation++; currentHome=null; working(false);
        screen("우리 집", "참여한 집을 확인하고 가족과 연결해요.");
        text(page,"집 목록을 확인하고 있어요…",16,MUTED,false);
        button(page,"다시 시도",false,this::homes);
        button(page,"연결 설정",false,this::connectionSettings);
        button(page,"로그아웃",false,this::logout);
        request("GET","/v1/me",null,result -> {
            userId=result.optString("user_id");
            screen("우리 집","참여한 집을 확인하고 가족과 연결해요.");
            JSONArray list=result.optJSONArray("homes");
            text(page,"참여한 집 "+(list==null ? 0 : list.length())+"개",14,MUTED,true);
            if(list==null || list.length()==0){ LinearLayout empty=card(); text(empty,"아직 연결된 집이 없어요",21,INK,true); text(empty,"내 집을 만들거나 가족에게 받은 초대를 수락해 주세요.",15,MUTED,false); }
            else for(int index=0;index<list.length();index++){
                JSONObject home=list.optJSONObject(index); if(home==null) continue;
                LinearLayout item=card(); text(item,role(home.optString("role")),12,GREEN,true);
                text(item,home.optString("name"),22,INK,true);
                button(item,"집 열기",false,()-> home(home.optString("id")));
            }
            button(page,"새 집 만들기",true,this::createHome);
            button(page,"가족 초대 수락",false,this::acceptInvitation);
            button(page,"새로고침",false,this::homes);
            if(BuildConfig.FLAVOR.equals("production")) button(page,"알림 설정",false,this::notificationSettings);
            button(page,"연결 설정",false,this::connectionSettings);
            button(page,"로그아웃",false,this::logout);
        });
    }
    private void singleInput(String title,String hint,int maximum,Consumer<String> action) {
        EditText input=new EditText(this); input.setSingleLine(); input.setHint(hint);
        input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(maximum)});
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(title).setView(input).setNegativeButton("취소",null).setPositiveButton("확인",null).create();
        dialog.setOnShowListener(unused -> dialog.getButton(-1).setOnClickListener(view -> {
            String value=input.getText().toString().trim(); if(value.isEmpty()){ input.setError("내용을 입력해 주세요."); return; }
            dialog.dismiss(); action.accept(value);
        })); dialog.show();
    }
    private void createHome() { singleInput("새 집 만들기","예: 우리 집",80,name -> request("POST","/v1/homes",json("name",name),reply -> home(reply.optString("id")))); }
    private void acceptInvitation(){ singleInput("가족 초대 수락","가족에게 받은 초대 코드",128,token -> request("POST","/v1/invitations/accept",json("invitation_token",token),reply -> home(reply.optString("home_id")))); }
    private void home(String id){
        viewMode="home";
        generation++; currentHome=id; working(false); screen("집 확인 중", "현재 가족 권한을 확인하고 있어요.");
        button(page,"집 목록으로",false,this::homes);
        request("GET","/v1/homes/"+id,null,house -> {
            screen(house.optString("name"),role(house.optString("role"))+" · 우리 가족의 스마트홈");
            LinearLayout alerts=card(); text(alerts,"이 휴대폰 알림",21,INK,true);
            android.content.SharedPreferences prefs=PushManager.prefs(this);
            text(alerts,!prefs.getBoolean("enabled",false) ? "꺼짐 · 원하는 알림을 선택하고 켜주세요."
                : prefs.getBoolean("registration_error",false) ? "연결 확인 필요"
                : prefs.getBoolean("preferences_pending",false) || !prefs.contains("binding") ? "연결 준비 중"
                : "연결됨 · 이 휴대폰의 선택에 따라 받아요.",14,MUTED,false);
            if(BuildConfig.FLAVOR.equals("production")) button(alerts,"받을 알림 선택",true,this::notificationSettings);
            if(house.optString("role").equals("owner") && BuildConfig.FLAVOR.equals("production"))
                button(alerts,"이 휴대폰에 시험 알림 보내기",false,()->testNotification(id));
            LinearLayout events=card(); text(events,"알림 기록",21,INK,true);
            text(events,"최근에 도착한 집의 이벤트를 확인해요.",14,MUTED,false);
            if(house.optString("role").equals("owner")) {
                LinearLayout manage=card(); text(manage,"집 관리",21,INK,true);
                text(manage,"가족 초대와 연결 기기는 소유자가 관리해요.",14,MUTED,false);
                button(manage,"가족 초대 만들기",false,()-> invite(id));
                button(manage,"가족 관리",false,()-> members(id));
                button(manage,"우리 집 기기 등록",false,()-> singleInput("우리 집 기기 등록","10분 동안 유효한 등록 코드",128,code -> request("POST","/v1/homes/"+id+"/hubs/claim",json("claim_code",code),reply -> {message("기기를 등록했어요."); home(id);} )));
                Button remove=button(manage,"이 집 삭제",false,()->deleteHome(id,house.optString("name")));
                remove.setTextColor(Color.rgb(160,55,45));
            }
            button(page,"집 새로고침",false,()-> home(id)); button(page,"집 목록으로",false,this::homes);
            button(page,"로그아웃",false,this::logout);
            request("GET","/v1/homes/"+id+"/events",null,reply -> {
                JSONArray list=reply.optJSONArray("events");
                if(list==null || list.length()==0) text(events,"아직 도착한 기록이 없어요",16,MUTED,false);
                else for(int index=0;index<list.length();index++){
                    JSONObject event=list.optJSONObject(index); if(event!=null) {
                        text(events,eventTitle(event),16,INK,true);
                        double received=event.optDouble("received_at",0);
                        if(received>0 && Double.isFinite(received)) text(events,
                            new java.text.SimpleDateFormat("MM월 dd일 HH:mm",java.util.Locale.KOREAN).format(new java.util.Date((long)(received*1000))),12,MUTED,false);
                    }
                }
            });
        });
    }
    private String eventTitle(JSONObject event) {
        String kind=event.optString("kind"); JSONObject payload=event.optJSONObject("payload");
        if(kind.equals("hub.connection_test")) return "기기 연결 시험";
        if(kind.equals("sensor.door_changed")) return payload!=null && payload.optString("state").equals("open") ? "문 열림" : "문 닫힘";
        if(kind.equals("automation.warning_triggered")) return "자동화 경고 발생";
        if(kind.equals("automation.warning_resolved")) return "자동화 경고 해제";
        if(kind.equals("sensor.climate_report")) {
            StringBuilder value=new StringBuilder("온습도 측정");
            if(payload!=null && payload.has("temperature_c")) value.append(" · ").append(String.format(java.util.Locale.KOREAN,"%.1f°C",payload.optDouble("temperature_c")));
            if(payload!=null && payload.has("humidity_percent")) value.append(" · ").append(String.format(java.util.Locale.KOREAN,"습도 %.0f%%",payload.optDouble("humidity_percent")));
            return value.toString();
        }
        return "집의 새 기록";
    }
    private void deleteHome(String id,String name) {
        EditText input=new EditText(this); input.setSingleLine(); input.setHint(name);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("이 집을 삭제할까요?")
            .setMessage("모든 가족의 집 목록에서 사라지고 연결 기기의 접근과 알림이 중지돼요.\n다시 사용하려면 새 집을 만들고 기기를 등록해야 해요.\n\n확인을 위해 집 이름을 입력해 주세요: "+name)
            .setView(input).setNegativeButton("취소",null).setPositiveButton("집 삭제",null).create();
        dialog.setOnShowListener(unused->dialog.getButton(-1).setOnClickListener(view->{
            if(!name.equals(input.getText().toString().trim())) { input.setError("집 이름을 정확히 입력해 주세요."); return; }
            dialog.dismiss(); request("DELETE","/v1/homes/"+id,json("confirmation_name",name),reply->{message("집을 삭제했어요.");homes();});
        }));dialog.show();
    }
    private void notificationHelp(String title,String detail) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(detail)
            .setPositiveButton("알림 설정",(dialog,which)->notificationSettings()).setNegativeButton("닫기",null).show();
    }
    private boolean notificationsAllowed() {
        android.app.NotificationManager manager=getSystemService(android.app.NotificationManager.class);
        android.app.NotificationChannel channel=manager.getNotificationChannel(PushManager.CHANNEL);
        return manager.areNotificationsEnabled() && (channel==null || channel.getImportance()!=android.app.NotificationManager.IMPORTANCE_NONE);
    }
    private void testNotification(String id) {
        android.content.SharedPreferences p=PushManager.prefs(this);
        if(!p.getBoolean("enabled",false) || !endpoint.equals(p.getString("origin",""))
                || !session.userId().equals(p.getString("account",""))) {
            notificationHelp("이 휴대폰 알림을 켜주세요","알림 설정에서 ‘이 휴대폰 알림 켜기’를 누르고 연결을 확인해 주세요.");
            return;
        }
        if(!notificationsAllowed()) {
            notificationHelp("휴대폰에서 알림을 허용해 주세요","휴대폰 설정에서 ‘가족 스마트홈’ 앱과 ‘우리 집 알림’의 알림을 허용해 주세요.");
            return;
        }
        if(p.getBoolean("registration_error",false)) {
            notificationHelp("알림 연결을 확인해 주세요",p.getString("registration_error_message","알림 설정에서 연결 상태를 확인한 뒤 다시 시도해 주세요."));
            return;
        }
        if(p.getString("binding","").isEmpty() || p.getBoolean("preferences_pending",false)) {
            PushManager.sync(this);
            notificationHelp("알림 연결 준비 중이에요","잠시 후 알림 설정에서 ‘알림 연결 확인’을 눌러 주세요. ‘알림 연결됨’이 되면 시험 알림을 보낼 수 있어요.");
            return;
        }
        request("POST","/v1/homes/"+id+"/notifications/test",json("installation_id",PushManager.installation(this)),reply ->
            message("알림 전송을 요청했어요. 휴대폰에 도착하는지 확인해 주세요."));
    }
    private void notificationSettings() {
        viewMode="notifications";
        screen("알림 설정","이 휴대폰에서 우리 집 알림을 받아요.");
        android.content.SharedPreferences p=PushManager.prefs(this);
        boolean enabled=p.getBoolean("enabled",false);
        text(page,!enabled ? "알림 받기 꺼짐" : p.getBoolean("registration_error",false) ? "알림 연결 확인 필요"
            : p.contains("binding") && !p.getBoolean("preferences_pending",false) ? "알림 연결됨" : "알림 연결 준비 중",20,INK,true);
        text(page,"Google 로그인과 별도로 이 휴대폰의 알림을 켜주세요. 다른 휴대폰의 설정에는 영향을 주지 않아요.",14,MUTED,false);
        if(enabled && p.getBoolean("registration_error",false))
            text(page,p.getString("registration_error_message","알림 연결에 실패했어요. 인터넷 연결을 확인한 뒤 다시 시도해 주세요."),15,MUTED,false);
        if(!notificationsAllowed()) {
            text(page,"휴대폰 설정에서 이 앱과 ‘우리 집 알림’의 알림을 허용해 주세요.",15,MUTED,false);
            button(page,"휴대폰 알림 설정 열기",false,()->startActivity(new android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName())));
        }
        if(p.getLong("last_received",0)>0) text(page,"최근 알림 수신 완료",15,GREEN,true);
        LinearLayout choice=card();text(choice,"받고 싶은 알림",21,INK,true);
        text(choice,"이 휴대폰에서 참여한 모든 집에 적용돼요.",14,MUTED,false);
        Switch door=new Switch(this);door.setText("문 열림·닫힘");door.setChecked(p.getBoolean("door",true));choice.addView(door);
        Switch warning=new Switch(this);warning.setText("자동화 경고 발생·해제");warning.setChecked(p.getBoolean("warning",true));choice.addView(warning);
        Switch climate=new Switch(this);climate.setText("온습도 측정");climate.setChecked(p.getBoolean("climate",false));choice.addView(climate);
        text(choice,"온습도 수신 간격",14,MUTED,true);
        Spinner interval=new Spinner(this); final int[] minutes={1,5,15,60};
        interval.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"1분","5분","15분","60분"}));
        for(int index=0;index<minutes.length;index++) if(minutes[index]==p.getInt("climate_interval_minutes",5)) interval.setSelection(index);
        interval.setEnabled(climate.isChecked());climate.setOnCheckedChangeListener((toggle,checked)->interval.setEnabled(checked));choice.addView(interval);
        text(choice,"선택한 간격이 지난 뒤 새 측정값이 들어오면 보내요. 새 값이 없으면 반복해서 보내지 않아요. 온습도 알림은 조용히 표시되며 절전 중에는 늦게 도착할 수 있어요.",13,MUTED,false);
        button(choice,"선택 저장",true,()->{
            PushManager.preferences(this,door.isChecked(),climate.isChecked(),warning.isChecked(),minutes[interval.getSelectedItemPosition()]);
            message(enabled ? "알림 선택을 적용하고 있어요. 연결 확인을 눌러 주세요." : "선택을 저장했어요. 아래에서 이 휴대폰 알림을 켜주세요.");notificationSettings();
        });
        button(page,"이 휴대폰 알림 켜기",true,()-> {
            if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                    !=android.content.pm.PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},70);
            else { PushManager.enable(this,endpoint,session.userId()); notificationSettings(); }
        });
        button(page,"이 휴대폰 알림 끄기",false,()-> {PushManager.disable(this); notificationSettings();});
        button(page,"알림 연결 확인",false,this::notificationSettings);
        button(page,"집 목록으로",false,this::homes);
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==70) {
            if(results.length>0 && results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED && session.userId()!=null)
                PushManager.enable(this,endpoint,session.userId());
            notificationSettings();
        }
    }
    private void invite(String id){
        singleInput("가족 Google 이메일","초대할 가족의 Google 이메일",254,email -> {
            new AlertDialog.Builder(this).setTitle("가족 권한 선택").setItems(new String[]{"가족","조회 전용"},(dialog,selection)->
                request("POST","/v1/homes/"+id+"/invitations",json("email",email,"role",selection==0 ? "member" : "viewer"),reply -> {
                    String code=reply.optString("invitation_token");
                    new AlertDialog.Builder(this).setTitle("초대 코드가 준비됐어요")
                        .setMessage("지정한 Google 계정만 수락할 수 있어요.\n한 번 사용 · 24시간 동안 유효\n\n복사한 코드는 가족에게 직접 전달해 주세요.")
                        .setPositiveButton("코드 복사",(d,w)-> {
                            ClipboardManager clipboard=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
                            clipboard.setPrimaryClip(ClipData.newPlainText("가족 초대 코드",code)); message("초대 코드를 복사했어요.");
                        }).setNegativeButton("닫기",null).show();
                })).show();
        });
    }
    private void members(String id){
        viewMode="members";
        generation++; working(false); screen("가족 관리","소유자가 가족의 권한을 관리해요.");
        button(page,"집으로 돌아가기",false,()->home(id));
        request("GET","/v1/homes/"+id+"/members",null,reply -> {
            JSONArray list=reply.optJSONArray("members"); if(list==null) return;
            for(int index=0;index<list.length();index++){
                JSONObject person=list.optJSONObject(index); if(person==null) continue;
                LinearLayout item=card(); text(item,person.optString("email"),16,INK,true);
                boolean active=person.optInt("active")==1;
                text(item,active ? role(person.optString("role")) : "참여 해제됨",13,MUTED,false);
                if(active && !person.optString("role").equals("owner")) {
                    button(item,"권한 변경",false,()-> new AlertDialog.Builder(this).setTitle("가족 권한 변경")
                        .setItems(new String[]{"가족","조회 전용"},(d,selection)->request("PATCH","/v1/homes/"+id+"/members/"+person.optString("id"),
                            json("role",selection==0 ? "member" : "viewer"),r -> members(id))).show());
                    button(item,"가족 참여 해제",false,()-> new AlertDialog.Builder(this).setTitle("가족 참여를 해제할까요?")
                        .setMessage("이 가족은 우리 집의 기록을 볼 수 없게 됩니다.").setNegativeButton("취소",null)
                        .setPositiveButton("참여 해제",(d,w)->request("POST","/v1/homes/"+id+"/members/"+person.optString("id")+"/revoke",json(),r -> members(id))).show());
                }
            }
        });
    }
}
