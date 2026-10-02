package com.aircon.family;

import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.Gravity;
import android.widget.*;
import androidx.activity.ComponentActivity;
import org.json.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
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
    private ScrollView scroll;
    private LinearLayout shell, footer;
    private String screenKey="";
    private final Map<String,Integer> scrollPositions=new HashMap<>();
    private JSONObject currentHouse;
    private JSONArray homeList=new JSONArray(), events=new JSONArray();
    private boolean eventsLoaded=false;
    private String eventFilter="all";
    private TextView pushStatus, pushDetail, pushReceipt, saveStatus;
    private Switch pushToggle;
    private boolean updatingPushControls;
    private final SharedPreferences.OnSharedPreferenceChangeListener pushListener=(prefs,key)->runOnUiThread(this::refreshPushStatus);
    private final List<Button> buttons=new ArrayList<>();
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private static final int INK=Color.rgb(24,35,57), MUTED=Color.rgb(91,103,122), GREEN=Color.rgb(45,79,193),
        BACKGROUND=Color.rgb(247,248,251), PALE=Color.rgb(234,239,255), LINE=Color.rgb(224,229,238), DANGER=Color.rgb(171,49,49);

    protected AuthSession createSession() { return new FirebaseSession(this); }
    protected String initialEndpoint() {
        return getPreferences(0).getString("endpoint",BuildConfig.DEBUG ? "http://127.0.0.1:8001" : "");
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        session=createSession(); endpoint=initialEndpoint(); loginPage();
        PushManager.prefs(this).registerOnSharedPreferenceChangeListener(pushListener);
        getOnBackPressedDispatcher().addCallback(this,new androidx.activity.OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() {
                generation++; working(false);
                if(viewMode.equals("members") || viewMode.equals("notifications")) settingsPage();
                else if(viewMode.equals("history") || viewMode.equals("settings")) { if(currentHome!=null) showHome(); else homes(); }
                else if(viewMode.equals("home")) homes();
                else moveTaskToBack(true);
            }
        });
    }
    @Override public void onResume() {
        super.onResume();
        if(session!=null && session.userId()==null && !viewMode.equals("login")){generation++;working(false);loginPage();return;}
        // Returning from a dialog, system settings or the Home button must keep this route and its draft.
        if (session!=null && session.userId()!=null && !busy && viewMode.equals("login")) {
            if(endpoint.isEmpty()) connectionPage(); else homes();
        }
        refreshPushStatus();
    }
    @Override public void onDestroy() {
        generation++; PushManager.prefs(this).unregisterOnSharedPreferenceChangeListener(pushListener);
        network.shutdownNow(); super.onDestroy();
    }
    private int dp(int number) { return (int)(number*getResources().getDisplayMetrics().density+.5f); }
    private GradientDrawable shape(int color, int radius) {
        GradientDrawable background=new GradientDrawable(); background.setColor(color); background.setCornerRadius(dp(radius)); return background;
    }
    private RippleDrawable ripple(int color,int radius) {
        return new RippleDrawable(ColorStateList.valueOf(Color.rgb(210,220,250)),shape(color,radius),shape(Color.WHITE,radius));
    }
    private void rememberScroll() {
        if(scroll!=null && !screenKey.isEmpty()) scrollPositions.put(screenKey,scroll.getScrollY());
    }
    private void restoreScroll(int y) {
        final ScrollView target=scroll;
        target.post(()->{ if(scroll==target) target.scrollTo(0,y); });
    }
    private void screen(String title, String subtitle) {
        rememberScroll();
        screenKey=viewMode+":"+(currentHome==null ? "" : currentHome);
        final int y=scrollPositions.getOrDefault(screenKey,0);
        buttons.clear();
        pushStatus=null;pushDetail=null;pushReceipt=null;pushToggle=null;saveStatus=null;
        shell=new LinearLayout(this); shell.setOrientation(LinearLayout.VERTICAL); shell.setBackgroundColor(BACKGROUND); shell.setTag("family_shell");
        shell.setOnApplyWindowInsetsListener((view,insets)-> {
            view.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom()); return insets;
        });
        LinearLayout bar=new LinearLayout(this);bar.setGravity(Gravity.CENTER_VERTICAL);bar.setPadding(dp(12),dp(8),dp(12),dp(8));
        if(viewMode.equals("notifications") || viewMode.equals("members")) iconButton(bar,"back","뒤로",this::settingsPage);
        LinearLayout titles=new LinearLayout(this);titles.setOrientation(LinearLayout.VERTICAL);
        bar.addView(titles,new LinearLayout.LayoutParams(0,-2,1));
        text(titles,title,22,INK,true); if(!subtitle.isEmpty()) text(titles,subtitle,12,MUTED,false);
        if(viewMode.equals("home") || viewMode.equals("history")) {
            iconButton(bar,"home","집 선택",this::homes);
            iconButton(bar,"refresh","집 새로고침",()->{if(viewMode.equals("history"))history();else home(currentHome);});
        }
        shell.addView(bar); divider(shell);
        scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setTag("family_scroll");
        scroll.setClipToPadding(false);scroll.setDescendantFocusability(android.view.ViewGroup.FOCUS_BEFORE_DESCENDANTS);
        scroll.setFocusableInTouchMode(true);
        page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),dp(20),dp(20),dp(24));
        scroll.addView(page);shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        footer=new LinearLayout(this);footer.setOrientation(LinearLayout.VERTICAL);shell.addView(footer);
        if(BuildConfig.FLAVOR.equals("fixture")) text(page,"동작 시험 · 가상 계정",12,Color.rgb(130,78,20),true);
        boolean signed=session!=null && session.userId()!=null && !viewMode.equals("connection") && !viewMode.equals("login");
        if(signed) navigationBar();
        setContentView(shell);restoreScroll(y);
    }
    private void replacePage(Runnable render) {
        int y=scroll.getScrollY();
        page.removeAllViews();buttons.removeIf(b->!insideShell(b));render.run();restoreScroll(y);
    }
    private boolean insideShell(View view) {
        android.view.ViewParent parent=view.getParent();
        while(parent instanceof View){if(parent==shell)return true;parent=parent.getParent();}return false;
    }
    private TextView text(LinearLayout parent,String value,int size,int color,boolean bold) {
        TextView view=new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        view.setPadding(0,dp(3),0,dp(3)); view.setLineSpacing(dp(2),1); parent.addView(view); return view;
    }
    private LinearLayout card() {
        LinearLayout value=new LinearLayout(this); value.setOrientation(LinearLayout.VERTICAL); value.setPadding(dp(16),dp(16),dp(16),dp(16));
        GradientDrawable bg=shape(Color.WHITE,18);bg.setStroke(dp(1),LINE);value.setBackground(bg);
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2); params.bottomMargin=dp(12); page.addView(value,params); return value;
    }
    private Button button(LinearLayout parent,String label,boolean primary,Runnable action) {
        Button view=new Button(this); flatten(view);view.setText(label); view.setAllCaps(false); view.setTextSize(15);
        view.setTextColor(primary ? Color.WHITE : GREEN); view.setBackground(ripple(primary ? GREEN : PALE,12));
        view.setMinHeight(dp(48));view.setPadding(dp(12),dp(8),dp(12),dp(8));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2); params.topMargin=dp(10); parent.addView(view,params);
        view.setEnabled(!busy); view.setOnClickListener(v -> { if (!busy) action.run(); }); buttons.add(view); return view;
    }
    private void iconButton(LinearLayout parent,String icon,String label,Runnable action) {
        Button button=new Button(this);flatten(button);button.setContentDescription(label);button.setBackground(ripple(Color.TRANSPARENT,12));
        button.setCompoundDrawables(null,new FamilyIcon(icon,GREEN,dp(22)),null,null);button.setPadding(dp(12),dp(12),dp(12),dp(12));
        parent.addView(button,new LinearLayout.LayoutParams(dp(48),dp(48)));button.setOnClickListener(v->{if(!busy)action.run();});
        button.setEnabled(!busy);buttons.add(button);
    }
    private void divider(LinearLayout parent) {
        View line=new View(this);line.setBackgroundColor(LINE);parent.addView(line,new LinearLayout.LayoutParams(-1,dp(1)));
    }
    private void gap(LinearLayout parent,int height) { parent.addView(new View(this),new LinearLayout.LayoutParams(1,dp(height))); }
    private void heading(String title,String caption) {
        text(page,title,25,INK,true);if(!caption.isEmpty())text(page,caption,14,MUTED,false);gap(page,16);
    }
    private Button row(LinearLayout parent,String icon,String label,String description,Runnable action) {
        Button row=new Button(this);flatten(row);row.setText(label+(description.isEmpty()?"":"\n"+description));row.setAllCaps(false);row.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);
        row.setTextSize(15);row.setTextColor(INK);row.setBackground(ripple(Color.TRANSPARENT,10));
        row.setCompoundDrawables(new FamilyIcon(icon,GREEN,dp(22)),null,new FamilyIcon("chevron",MUTED,dp(18)),null);
        row.setCompoundDrawablePadding(dp(12));row.setPadding(dp(8),dp(14),dp(8),dp(14));row.setMinHeight(dp(56));
        parent.addView(row,new LinearLayout.LayoutParams(-1,-2));row.setOnClickListener(v->{if(!busy)action.run();});row.setEnabled(!busy);buttons.add(row);return row;
    }
    private void navigationBar() {
        divider(shell);
        LinearLayout nav=new LinearLayout(this);nav.setBackgroundColor(Color.WHITE);nav.setPadding(dp(10),dp(6),dp(10),dp(6));
        String selected=viewMode.equals("history") ? "기록" : viewMode.equals("settings") || viewMode.equals("notifications") || viewMode.equals("members") ? "설정" : "홈";
        String[] labels={"홈","기록","설정"}, icons={"home","history","settings"};
        Runnable[] actions={()->{if(currentHome!=null)showHome();else homes();},this::history,this::settingsPage};
        for(int i=0;i<labels.length;i++) {
            final Runnable action=actions[i];Button item=new Button(this);flatten(item);boolean active=labels[i].equals(selected);
            item.setText(labels[i]);item.setTextSize(12);item.setAllCaps(false);item.setTextColor(active?GREEN:MUTED);
            item.setCompoundDrawables(null,new FamilyIcon(icons[i],active?GREEN:MUTED,dp(22)),null,null);
            item.setCompoundDrawablePadding(dp(4));item.setPadding(0,dp(6),0,dp(6));item.setBackground(ripple(active?PALE:Color.WHITE,14));
            item.setSelected(active);item.setOnClickListener(v->{if(!busy && (!item.isSelected() || viewMode.equals("notifications") || viewMode.equals("members")))action.run();});item.setEnabled(!busy);buttons.add(item);
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(60),1);p.setMargins(dp(5),0,dp(5),0);nav.addView(item,p);
        }
        shell.addView(nav);
    }
    private void flatten(Button button) {button.setStateListAnimator(null);button.setElevation(0);}
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
        currentHome=null; currentHouse=null; userId=null; homeList=new JSONArray();events=new JSONArray();eventsLoaded=false;scrollPositions.clear();
        screen("가족 스마트홈", "");
        gap(page,30);
        TextView mark=text(page,"",48,GREEN,true);mark.setCompoundDrawables(new FamilyIcon("home",GREEN,dp(56)),null,null,null);
        gap(page,20);heading("우리 집을 함께","가족만 연결되는 나의 스마트홈");
        text(page,"문이 열릴 때, 집에 변화가 있을 때.\n어디서든 우리 집 소식을 받아보세요.",17,MUTED,false);gap(page,24);
        LinearLayout intro=card();
        text(intro,"같은 집, 각자의 계정",18,INK,true);
        text(intro,"내 집을 만들거나 가족의 초대를 받아 시작해요.",14,MUTED,false);
        button(intro,"Google로 계속하기",true,()-> {
            working(true); int epoch=generation;
            session.signIn(()-> { if(epoch==generation && !isDestroyed()){ working(false); if(endpoint.isEmpty()) connectionPage(); else homes(); } },error -> {
                if(epoch==generation && !isDestroyed()){ working(false); message(error); }
            });
        });
        button(page,"연결 설정",false,this::connectionSettings);
        gap(page,16);text(page,"집 소유자가 초대한 가족만 참여할 수 있어요.",13,MUTED,false);
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
        generation++; currentHome=null;currentHouse=null;eventsLoaded=false;working(false);
        screen("우리 집", "가족 스마트홈");
        renderHomes(homeList);
        request("GET","/v1/me",null,result -> {
            userId=result.optString("user_id");
            homeList=result.optJSONArray("homes");if(homeList==null)homeList=new JSONArray();
            replacePage(()->renderHomes(homeList));
        });
    }
    private void renderHomes(JSONArray list) {
        heading("나의 공간","집을 선택하면 상태와 기록을 볼 수 있어요.");
        text(page,"참여한 집 "+list.length()+"개",13,MUTED,true);gap(page,12);
        if(list.length()==0) {
            LinearLayout empty=card();text(empty,"아직 연결된 집이 없어요",19,INK,true);
            text(empty,"새 집을 만들거나 가족이 보낸 초대를 수락해 주세요.",14,MUTED,false);
        }
        for(int i=0;i<list.length();i++) {
            JSONObject house=list.optJSONObject(i);if(house==null)continue;
            LinearLayout item=card();TextView name=text(item,house.optString("name"),20,INK,true);
            name.setCompoundDrawables(new FamilyIcon("home",GREEN,dp(22)),null,null,null);name.setCompoundDrawablePadding(dp(10));
            text(item,role(house.optString("role")),13,MUTED,false);
            button(item,"집 열기",false,()->home(house.optString("id")));
        }
        button(page,"새 집 만들기",true,this::createHome);
        row(page,"family","가족 초대 수락","",this::acceptInvitation);
        row(page,"refresh","새로고침","",this::homes);
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
        generation++;if(!id.equals(currentHome)){currentHouse=null;events=new JSONArray();eventsLoaded=false;eventFilter="all";}
        currentHome=id;working(false);
        screen(currentHouse==null?"우리 집":currentHouse.optString("name"),currentHouse==null?"집을 확인하고 있어요":role(currentHouse.optString("role"))+" · 우리 가족의 스마트홈");
        if(currentHouse==null)text(page,"가족 권한과 기록을 확인하고 있어요…",15,MUTED,false);else renderHome();
        request("GET","/v1/homes/"+id,null,house -> {
            currentHouse=house;
            // The header changes once the name arrives; keep the loading route's saved offset.
            screen(house.optString("name"),role(house.optString("role"))+" · 우리 가족의 스마트홈");renderHome();
            request("GET","/v1/homes/"+id+"/events",null,reply -> {
                events=reply.optJSONArray("events");if(events==null)events=new JSONArray();eventsLoaded=true;
                replacePage(this::renderHome);
            });
        });
    }
    private void showHome() {
        if(currentHome==null){homes();return;}if(currentHouse==null){home(currentHome);return;}
        generation++;working(false);viewMode="home";
        screen(currentHouse.optString("name"),role(currentHouse.optString("role"))+" · 우리 가족의 스마트홈");renderHome();
    }
    private JSONObject latest(String kind) {
        JSONObject result=null;double received=-1;
        for(int i=0;i<events.length();i++) {JSONObject e=events.optJSONObject(i);if(e!=null && kind.equals(e.optString("kind")) && e.optDouble("received_at",0)>received){result=e;received=e.optDouble("received_at",0);}}
        return result;
    }
    private String eventTime(JSONObject event) {
        double t=event.optDouble("received_at",0);if(t<=0 || !Double.isFinite(t))return "시각 정보 없음";
        return new java.text.SimpleDateFormat("MM월 dd일 HH:mm",java.util.Locale.KOREAN).format(new java.util.Date((long)(t*1000)));
    }
    private void sensorTile(LinearLayout grid,String icon,String title,String value,String caption) {
        LinearLayout tile=new LinearLayout(this);tile.setOrientation(LinearLayout.VERTICAL);tile.setPadding(dp(14),dp(16),dp(14),dp(16));tile.setBackground(shape(Color.WHITE,18));
        TextView label=text(tile,title,14,MUTED,true);label.setCompoundDrawables(new FamilyIcon(icon,GREEN,dp(20)),null,null,null);label.setCompoundDrawablePadding(dp(8));
        gap(tile,10);text(tile,value,21,INK,true);gap(tile,4);text(tile,caption,12,MUTED,false);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-1,1);p.setMargins(0,0,dp(8),0);grid.addView(tile,p);
    }
    private void renderHome() {
        heading("우리 집 한눈에","마지막으로 받은 기록을 모아봤어요.");
        if(BuildConfig.FLAVOR.equals("production")) {
            LinearLayout alerts=card();alerts.setBackground(shape(PALE,18));
            text(alerts,"이 휴대폰 알림",13,GREEN,true);pushStatus=text(alerts,"",20,INK,true);pushDetail=text(alerts,"",13,MUTED,false);
            button(alerts,"받을 알림 선택",true,this::notificationSettings);refreshPushStatus();
        }
        JSONObject door=latest("sensor.door_changed"), climate=latest("sensor.climate_report");
        LinearLayout grid=new LinearLayout(this);grid.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams gp=new LinearLayout.LayoutParams(-1,-2);gp.bottomMargin=dp(20);page.addView(grid,gp);
        JSONObject d=door==null?null:door.optJSONObject("payload"), c=climate==null?null:climate.optJSONObject("payload");
        String doorValue=d==null?"—":d.optString("state").equals("open")?"열림":"닫힘";
        String climateValue=c!=null&&c.has("temperature_c")?String.format(java.util.Locale.KOREAN,"%.1f°C",c.optDouble("temperature_c")):"—";
        sensorTile(grid,"door","문 상태",doorValue,door==null?"아직 기록 없음":eventTime(door));
        String climateCaption=c!=null&&c.has("humidity_percent")?String.format(java.util.Locale.KOREAN,"습도 %.0f%%\n",c.optDouble("humidity_percent")):"";
        sensorTile(grid,"climate","온습도",climateValue,climate==null?"아직 기록 없음":climateCaption+eventTime(climate));
        text(page,"최근 기록",19,INK,true);gap(page,8);LinearLayout recent=card();
        renderEventList(recent,3,"all");row(recent,"history","모든 기록 보기","",this::history);
        if(currentHouse!=null && "owner".equals(currentHouse.optString("role")) && BuildConfig.FLAVOR.equals("production"))
            row(page,"bell","이 휴대폰에 시험 알림 보내기","",()->testNotification(currentHome));
        text(page,"가족 초대와 기기 등록은 설정에서 관리해요.",12,MUTED,false);
    }
    private String eventCategory(JSONObject event) {
        String kind=event.optString("kind");return kind.equals("sensor.door_changed")?"door":kind.equals("sensor.climate_report")?"climate":kind.startsWith("automation.warning_")?"warning":"other";
    }
    private void renderEventList(LinearLayout parent,int limit,String filter) {
        parent.removeAllViews();int shown=0;
        if(!eventsLoaded){text(parent,"기록을 확인하고 있어요…",14,MUTED,false);return;}
        for(int i=0;i<events.length() && shown<limit;i++) {
            JSONObject event=events.optJSONObject(i);if(event==null || (!filter.equals("all")&&!eventCategory(event).equals(filter)))continue;
            if(shown>0)divider(parent);
            LinearLayout entry=new LinearLayout(this);entry.setOrientation(LinearLayout.VERTICAL);entry.setPadding(0,dp(10),0,dp(10));parent.addView(entry);
            TextView title=text(entry,eventTitle(event),15,INK,true);String cat=eventCategory(event);
            title.setCompoundDrawables(new FamilyIcon(cat.equals("other")?"hub":cat,GREEN,dp(21)),null,null,null);title.setCompoundDrawablePadding(dp(10));
            TextView time=text(entry,eventTime(event),12,MUTED,false);time.setPadding(dp(31),dp(3),0,dp(3));shown++;
        }
        if(shown==0) {text(parent,filter.equals("all")?"아직 도착한 기록이 없어요":"이 종류의 기록은 아직 없어요",16,INK,true);text(parent,"집에서 새 소식이 오면 여기에 표시돼요.",14,MUTED,false);}
    }
    private void history() {
        if(currentHome==null){message("먼저 집을 선택해 주세요.");homes();return;}
        generation++;working(false);viewMode="history";screen("집의 기록",currentHouse==null?"":currentHouse.optString("name"));
        heading("집에서 일어난 일","최근 기록을 종류별로 살펴보세요.");
        LinearLayout filters=new LinearLayout(this);filters.setOrientation(LinearLayout.HORIZONTAL);page.addView(filters);gap(page,16);
        LinearLayout list=card();String[] labels={"전체","문","온습도","경고"}, kinds={"all","door","climate","warning"};List<Button> chips=new ArrayList<>();
        for(int i=0;i<labels.length;i++) {
            final String kind=kinds[i];Button chip=new Button(this);flatten(chip);chip.setText(labels[i]);chip.setAllCaps(false);chip.setTextSize(14);chip.setMinHeight(dp(48));
            chip.setBackground(ripple(eventFilter.equals(kind)?GREEN:Color.WHITE,24));chip.setTextColor(eventFilter.equals(kind)?Color.WHITE:MUTED);chip.setTag(kind);
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(48),1);p.rightMargin=dp(6);filters.addView(chip,p);chips.add(chip);
            chip.setOnClickListener(v->{eventFilter=kind;for(Button b:chips){boolean active=kind.equals(b.getTag());b.setTextColor(active?Color.WHITE:MUTED);b.setBackground(ripple(active?GREEN:Color.WHITE,24));}int y=scroll.getScrollY();renderEventList(list,50,kind);restoreScroll(y);});
        }
        renderEventList(list,50,eventFilter);text(page,"기록 시각은 이 휴대폰의 시간대 기준이에요.",12,MUTED,false);
        request("GET","/v1/homes/"+currentHome+"/events",null,reply->{events=reply.optJSONArray("events");if(events==null)events=new JSONArray();eventsLoaded=true;int y=scroll.getScrollY();renderEventList(list,50,eventFilter);restoreScroll(y);});
    }
    private void settingsPage() {
        generation++;working(false);viewMode="settings";screen("설정",currentHouse==null?"내 계정과 휴대폰":currentHouse.optString("name"));
        text(page,"이 휴대폰",13,MUTED,true);gap(page,8);LinearLayout phone=card();
        if(BuildConfig.FLAVOR.equals("production"))row(phone,"bell","알림 설정","",this::notificationSettings);
        text(phone,"알림 종류와 온습도 수신 간격을 선택해요.",13,MUTED,false);
        if(currentHouse!=null) {
            text(page,"집 관리",13,MUTED,true);gap(page,8);LinearLayout house=card();
            text(house,currentHouse.optString("name"),18,INK,true);text(house,role(currentHouse.optString("role"))+" · 우리 가족의 스마트홈",12,MUTED,false);gap(house,8);
            if("owner".equals(currentHouse.optString("role"))) {
                row(house,"family","가족 초대 만들기","",()->invite(currentHome));divider(house);
                row(house,"family","가족 관리","",()->members(currentHome));divider(house);
                row(house,"hub","우리 집 기기 등록","",()->singleInput("우리 집 기기 등록","10분 동안 유효한 등록 코드",128,code->request("POST","/v1/homes/"+currentHome+"/hubs/claim",json("claim_code",code),reply->{message("기기를 등록했어요.");settingsPage();})));
            } else text(house,"가족 초대와 기기 등록은 소유자가 관리해요.",14,MUTED,false);
            divider(house);row(house,"home","집 목록으로","",this::homes);
        } else {LinearLayout choose=card();row(choose,"home","집 목록으로","",this::homes);}
        text(page,"연결 및 계정",13,MUTED,true);gap(page,8);LinearLayout account=card();
        row(account,"network","연결 설정","",this::connectionSettings);divider(account);row(account,"logout","로그아웃","",this::logout);
        if(currentHouse!=null && "owner".equals(currentHouse.optString("role"))) {
            LinearLayout danger=card();Button remove=row(danger,"trash","이 집 삭제","",()->deleteHome(currentHome,currentHouse.optString("name")));remove.setTextColor(DANGER);
            text(danger,"모든 가족의 접근과 연결 기기의 알림이 중지돼요.",12,MUTED,false);
        }
        text(page,"가족 스마트홈 · "+BuildConfig.VERSION_NAME,12,MUTED,false);
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
            notificationHelp("이 휴대폰 알림을 켜주세요","알림 설정에서 ‘이 휴대폰에서 받기’를 켜고 연결을 확인해 주세요.");
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
    private String pushState() {
        SharedPreferences p=PushManager.prefs(this);
        if(!p.getBoolean("enabled",false))return "알림 받기 꺼짐";
        if(!notificationsAllowed())return "휴대폰 알림 허용 필요";
        if(p.getBoolean("registration_error",false))return "알림 연결 확인 필요";
        return !p.getString("binding","").isEmpty() && !p.getBoolean("preferences_pending",false)?"알림 연결됨":"알림 연결 준비 중";
    }
    private void refreshPushStatus() {
        if(isDestroyed() || pushStatus==null)return;
        SharedPreferences p=PushManager.prefs(this);boolean enabled=p.getBoolean("enabled",false);
        pushStatus.setText(pushState());
        String detail=!enabled?"알림을 켜고 받고 싶은 소식을 선택해 주세요.":!notificationsAllowed()?"휴대폰 설정에서 앱 알림을 허용해 주세요."
            :p.getBoolean("registration_error",false)?p.getString("registration_error_message","인터넷 연결을 확인한 뒤 다시 시도해 주세요.")
            :p.getBoolean("preferences_pending",false)||p.getString("binding","").isEmpty()?"휴대폰을 연결하고 선택한 설정을 적용하고 있어요.":"선택한 소식만 이 휴대폰으로 보내드려요.";
        if(pushDetail!=null)pushDetail.setText(detail);
        if(pushReceipt!=null){pushReceipt.setVisibility(p.getLong("last_received",0)>0?View.VISIBLE:View.GONE);pushReceipt.setText("최근 알림 수신 완료");}
        if(pushToggle!=null){updatingPushControls=true;pushToggle.setChecked(enabled);updatingPushControls=false;}
    }
    private Switch preferenceSwitch(LinearLayout parent,String label,boolean checked) {
        Switch toggle=new Switch(this);toggle.setText(label);toggle.setTextSize(15);toggle.setTextColor(INK);toggle.setChecked(checked);
        toggle.setMinHeight(dp(60));toggle.setPadding(0,dp(10),0,dp(10));parent.addView(toggle,new LinearLayout.LayoutParams(-1,-2));return toggle;
    }
    private void enableNotifications() {
        if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},70);
        else {PushManager.enable(this,endpoint,session.userId());refreshPushStatus();}
    }
    private void notificationSettings() {
        generation++;working(false);viewMode="notifications";
        screen("알림 설정","이 휴대폰에만 적용돼요");
        SharedPreferences p=PushManager.prefs(this);
        LinearLayout state=card();state.setBackground(shape(PALE,18));
        pushStatus=text(state,"",20,INK,true);pushDetail=text(state,"",14,MUTED,false);
        pushToggle=preferenceSwitch(state,"이 휴대폰에서 받기",p.getBoolean("enabled",false));
        pushToggle.setOnCheckedChangeListener((v,checked)->{if(updatingPushControls)return;if(checked)enableNotifications();else {PushManager.disable(this);refreshPushStatus();}});
        pushReceipt=text(state,"최근 알림 수신 완료",12,GREEN,true);
        row(state,"refresh","알림 연결 확인","",()->{PushManager.sync(this);refreshPushStatus();message("연결 상태를 확인하고 있어요.");});
        text(page,"받고 싶은 알림",19,INK,true);text(page,"참여한 모든 집에 같은 선택을 적용해요.",13,MUTED,false);gap(page,12);
        LinearLayout choice=card();
        Switch door=preferenceSwitch(choice,"문 열림·닫힘",p.getBoolean("door",true));divider(choice);
        Switch warning=preferenceSwitch(choice,"자동화 경고 발생·해제",p.getBoolean("warning",true));divider(choice);
        Switch climate=preferenceSwitch(choice,"온습도 측정",p.getBoolean("climate",false));
        text(choice,"온습도 수신 간격",13,MUTED,true);gap(choice,8);
        LinearLayout intervals=new LinearLayout(this);choice.addView(intervals,new LinearLayout.LayoutParams(-1,-2));
        int[] minutes={1,5,15,60};int[] selected={p.getInt("climate_interval_minutes",5)};List<Button> options=new ArrayList<>();
        Runnable styleOptions=()->{for(Button b:options){boolean active=((Integer)b.getTag())==selected[0];b.setTextColor(active?Color.WHITE:MUTED);b.setBackground(ripple(active?GREEN:BACKGROUND,12));b.setEnabled(climate.isChecked());b.setAlpha(climate.isChecked()?1:.55f);}};
        for(int minute:minutes){
            Button option=new Button(this);flatten(option);option.setText(minute+"분");option.setTextSize(14);option.setAllCaps(false);option.setPadding(0,0,0,0);option.setTag(minute);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(48),1);lp.rightMargin=dp(4);intervals.addView(option,lp);options.add(option);
            option.setOnClickListener(v->{selected[0]=minute;styleOptions.run();saveStatus.setText("변경한 선택을 저장해 주세요.");});
        }
        styleOptions.run();
        text(choice,"새 측정값이 있을 때만 보내요. 온습도 알림은 조용히 표시돼요.",13,MUTED,false);
        row(page,"settings","휴대폰 알림 설정 열기","",()->startActivity(new android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName())));
        row(page,"home","집 목록으로","",this::homes);
        LinearLayout help=card();text(help,"휴대폰마다 취향대로",16,INK,true);
        text(help,"다른 휴대폰의 알림 선택은 바뀌지 않아요.\n온습도는 절전 중 늦게 도착할 수 있어요.",13,MUTED,false);
        footer.setBackgroundColor(Color.WHITE);footer.setPadding(dp(20),dp(8),dp(20),dp(12));divider(footer);
        saveStatus=text(footer,"이 휴대폰의 설정만 바뀌어요.",12,MUTED,false);
        button(footer,"선택 저장",true,()->{
            PushManager.preferences(this,door.isChecked(),climate.isChecked(),warning.isChecked(),selected[0]);
            saveStatus.setText("선택을 저장했어요.");saveStatus.setTextColor(GREEN);refreshPushStatus();
        });
        android.widget.CompoundButton.OnCheckedChangeListener changed=(v,checked)->{styleOptions.run();saveStatus.setText("변경한 선택을 저장해 주세요.");saveStatus.setTextColor(MUTED);};
        door.setOnCheckedChangeListener(changed);warning.setOnCheckedChangeListener(changed);climate.setOnCheckedChangeListener(changed);
        refreshPushStatus();
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==70) {
            if(results.length>0 && results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED && session.userId()!=null)
                PushManager.enable(this,endpoint,session.userId());
            refreshPushStatus();
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
