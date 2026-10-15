package com.aircon.family;

import android.app.AlertDialog;
import android.app.TimePickerDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.InsetDrawable;
import android.graphics.drawable.LayerDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.text.style.RelativeSizeSpan;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;
import androidx.activity.ComponentActivity;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/**
 * Native family UI. Identity is obtained only through Firebase, never from Intent extras.
 * Top-level tabs 홈 / 알림 / 설정 show the bottom navigation; detail screens (기기, 에어컨, 종류, 가족 관리)
 * have a back arrow instead and return through {@link #backStack}.
 */
public class FamilyActivity extends ComponentActivity {
    protected AuthSession session;
    private String endpoint, userId, currentHome;
    /** Current screen and its argument (device id or category key). */
    private String viewMode="login", routeArg="";
    private final ArrayList<String[]> backStack=new ArrayList<>();
    private int generation=0;
    private boolean busy=false;
    private LinearLayout page;
    private ScrollView scroll;
    private LinearLayout shell, footer;
    private String screenKey="";
    private final Map<String,Integer> scrollPositions=new HashMap<>();
    private JSONObject currentHouse;
    private String homeError;
    private final HomeListState<JSONArray> homeList=new HomeListState<>(new JSONArray());
    private List<AppEvent> events=new ArrayList<>();
    private boolean eventsLoaded=false;
    private String eventsError;
    /** The server's device list; null before it loads, after a failure, or on a server older than 0.7 (404). */
    private Inventory serverInventory;
    private boolean devicesLoaded=false;
    private JSONObject aircon;
    private String airconError;
    private boolean airconLoaded=false;
    private String selectedAircon;
    private final Map<String,AirconUi.Draft> airconDrafts=new HashMap<>();
    private final CommandPoll poll=new CommandPoll();
    private final android.os.Handler ui=new android.os.Handler(android.os.Looper.getMainLooper());
    private boolean stopped, resumeAircon;
    private AlertDialog commandDialog, identityDialog, switcherDialog;
    private String eventFilter="all";
    private final Set<String> expanded=new HashSet<>();
    private TextView pushStatus, pushDetail, pushReceipt, headerTitle, headerSubtitle, bellBadge;
    private Button bellButton;
    private Switch pushToggle;
    private boolean updatingPushControls;
    private final SharedPreferences.OnSharedPreferenceChangeListener pushListener=(prefs,key)->runOnUiThread(this::refreshPushStatus);
    private final List<Button> buttons=new ArrayList<>();
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    /** Dark smart-home palette (styles.xml mirrors the page, accent and dialog colours). */
    private static final int BACKGROUND=0xFF0F1724, SURFACE=0xFF162133, RAISED=0xFF1E2A3D, LINE=0xFF2B3A52,
        INK=0xFFE6EDF7, MUTED=0xFF9AA8BC, ACCENT=0xFF37A8DD, ON_ACCENT=0xFF0F1724, ONLINE=0xFF5DCAA5, ONLINE_SURFACE=0x265DCAA5,
        DANGER=0xFFF09595, DANGER_SURFACE=0xFF3A1D22, WARNING=0xFFEF9F27, WARNING_SURFACE=0xFF3A2E1A,
        RIPPLE_LIGHT=0x33E6EDF7, RIPPLE_DARK=0x400F1724;
    private static final Set<String> KNOWN_STATE=new HashSet<>(Arrays.asList("contact","battery_percent","battery_low","temperature_c",
        "humidity_percent","power","brightness_percent","color_temp_k","power_w","motion","leak","smoke","mode","setpoint_c","fan","inferred"));
    private static final Set<String> KNOWN_CAPABILITIES=new HashSet<>(Arrays.asList("contact","battery","temperature","humidity","power",
        "brightness","color_temp","power_meter","motion","leak","smoke","setpoint","mode","fan","actions"));

    protected AuthSession createSession() { return new FirebaseSession(this); }
    protected String initialEndpoint() {
        return getPreferences(0).getString("endpoint",BuildConfig.DEBUG ? "http://127.0.0.1:8001" : "");
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        session=createSession(); endpoint=initialEndpoint(); if(!restore(state)) loginPage();
        PushManager.prefs(this).registerOnSharedPreferenceChangeListener(pushListener);
        getOnBackPressedDispatcher().addCallback(this,new androidx.activity.OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() { back(); }
        });
    }
    @Override public void onResume() {
        super.onResume();
        if(session!=null && session.userId()==null && !viewMode.equals("login")){generation++;working(false);loginPage();return;}
        // Returning from a dialog, system settings or the Home button must keep this route and its scroll position.
        if (session!=null && session.userId()!=null && !busy && viewMode.equals("login")) {
            if(endpoint.isEmpty()) connectionPage(); else start();
        } else if (session!=null && session.userId()!=null && !busy && viewMode.equals("start") && homeList.refreshing()) {
            // A home list request abandoned by back/Home would otherwise keep the loading card with nothing in flight.
            start();
        }
        refreshPushStatus();
    }
    @Override public void onStart() {
        super.onStart(); stopped=false;
        // A result check interrupted in the background resumes from the server's latest command.
        if(resumeAircon){ resumeAircon=false; loadAircon(); }
    }
    @Override public void onStop() {
        stopped=true; if(poll.cancel()) resumeAircon=true; ui.removeCallbacksAndMessages(null); super.onStop();
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putString("view_mode",viewMode); state.putString("route",routeArg); state.putString("home",currentHome); state.putString("aircon",selectedAircon);
        ArrayList<String> modes=new ArrayList<>(), args=new ArrayList<>();
        for(String[] route:backStack){ modes.add(route[0]); args.add(route[1]); }
        state.putStringArrayList("back_modes",modes); state.putStringArrayList("back_args",args);
        ArrayList<String> keys=new ArrayList<>(airconDrafts.keySet()); int[] values=new int[keys.size()*3];
        for(int i=0;i<keys.size();i++) System.arraycopy(airconDrafts.get(keys.get(i)).save(),0,values,i*3,3);
        state.putStringArrayList("draft_keys",keys); state.putIntArray("draft_values",values);
    }
    /** Process death or an unhandled configuration change keeps the open home, the open screen, its back path and unsent drafts. */
    private boolean restore(Bundle state) {
        String home=state==null ? null : state.getString("home");
        if(home==null || session.userId()==null || endpoint.isEmpty()) return false;
        ArrayList<String> keys=state.getStringArrayList("draft_keys"); int[] values=state.getIntArray("draft_values");
        if(keys!=null) for(int i=0;i<keys.size();i++) airconDrafts.put(keys.get(i),AirconUi.Draft.restore(values,i*3));
        currentHome=home; selectedAircon=state.getString("aircon");
        ArrayList<String> modes=state.getStringArrayList("back_modes"), args=state.getStringArrayList("back_args");
        if(modes!=null && args!=null && modes.size()==args.size())
            for(int i=0;i<modes.size();i++) if(inHome(modes.get(i))) backStack.add(new String[]{modes.get(i),args.get(i)==null ? "" : args.get(i)});
        String mode=state.getString("view_mode","home"), arg=state.getString("route","");
        if(mode==null || !inHome(mode)) mode="home";
        if(arg==null) arg="";
        if(mode.equals("aircon") && arg.isEmpty() && selectedAircon!=null) arg=selectedAircon;
        show(mode,arg);
        return true;
    }
    @Override public void onDestroy() {
        generation++; ui.removeCallbacksAndMessages(null); PushManager.prefs(this).unregisterOnSharedPreferenceChangeListener(pushListener);
        network.shutdownNow(); super.onDestroy();
    }

    // ---- Navigation ----

    private static boolean inHome(String mode) {
        return mode.equals("home") || mode.equals("alerts") || mode.equals("settings") || mode.equals("members")
            || mode.equals("aircon") || mode.equals("device") || mode.equals("category");
    }
    private static boolean tabMode(String mode) { return mode.equals("home") || mode.equals("alerts") || mode.equals("settings"); }
    /** Renders a screen of the open home without touching the back path. */
    private void show(String mode,String arg) {
        if(currentHome==null){ start(); return; }
        switch(mode) {
            case "alerts": alertsPage(); break;
            case "settings": settingsPage(); break;
            case "members": members(); break;
            case "aircon": airconPage(arg); break;
            case "device": devicePage(arg); break;
            case "category": categoryPage(arg); break;
            default: showHome();
        }
    }
    /** Opens a detail screen; back returns to the current one. */
    private void open(String mode,String arg) {
        if(inHome(viewMode)) backStack.add(new String[]{viewMode,routeArg});
        show(mode,arg);
    }
    /** Top-level tab: the back path starts over. */
    private void tab(String mode) { backStack.clear(); show(mode,""); }
    private void back() {
        generation++; working(false);
        if(!backStack.isEmpty()) { String[] route=backStack.remove(backStack.size()-1); show(route[0],route[1]); return; }
        if(inHome(viewMode) && !viewMode.equals("home")) { tab("home"); return; }
        moveTaskToBack(true);
    }
    private void openDevice(Device device) { open(device.aircon() ? "aircon" : "device",device.id); }

    // ---- Drawing helpers ----

    private int dp(int number) { return (int)(number*getResources().getDisplayMetrics().density+.5f); }
    private GradientDrawable shape(int color, int radius) {
        GradientDrawable background=new GradientDrawable(); background.setColor(color); background.setCornerRadius(dp(radius)); return background;
    }
    private GradientDrawable oval(int color) {
        GradientDrawable background=new GradientDrawable(); background.setShape(GradientDrawable.OVAL); background.setColor(color); return background;
    }
    /** Light wash on dark surfaces, dark wash on the accent fill. The mask only limits the ripple and is never drawn. */
    private RippleDrawable ripple(int color,int radius) {
        return new RippleDrawable(ColorStateList.valueOf(color==ACCENT?RIPPLE_DARK:RIPPLE_LIGHT),shape(color,radius),shape(INK,radius));
    }
    private RippleDrawable rippleOval(int color) {
        return new RippleDrawable(ColorStateList.valueOf(color==ACCENT?RIPPLE_DARK:RIPPLE_LIGHT),oval(color),oval(INK));
    }
    /** A filled circle with a centred line icon; used for mode buttons, badges and the round footer/step buttons. */
    private Drawable circleIcon(String icon,int fill,int iconColor,int size,int iconSize) {
        LayerDrawable layers=new LayerDrawable(new Drawable[]{rippleOval(fill),new FamilyIcon(icon,iconColor,dp(iconSize))});
        int inset=dp(size-iconSize)/2; layers.setLayerInset(1,inset,inset,inset,inset); return layers;
    }
    private View badge(LinearLayout parent,String icon,int fill,int iconColor,int size,int iconSize) {
        View view=new View(this);view.setBackground(circleIcon(icon,fill,iconColor,size,iconSize));
        view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        parent.addView(view,new LinearLayout.LayoutParams(dp(size),dp(size)));return view;
    }
    private View icon(LinearLayout parent,String name,int color,int size) {
        View view=new View(this);view.setBackground(new FamilyIcon(name,color,dp(size)));
        view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        parent.addView(view,new LinearLayout.LayoutParams(dp(size),dp(size)));return view;
    }
    /** Pill chip: outlined when idle, accent-filled when active. The pill is 36dp tall inside a 48dp touch target. */
    private Drawable chipBackground(boolean active) {
        GradientDrawable fill=shape(active?ACCENT:Color.TRANSPARENT,24);if(!active)fill.setStroke(dp(1),LINE);
        return new RippleDrawable(ColorStateList.valueOf(active?RIPPLE_DARK:RIPPLE_LIGHT),
            new InsetDrawable(fill,0,dp(6),0,dp(6)),new InsetDrawable(shape(INK,24),0,dp(6),0,dp(6)));
    }
    private void chipStyle(Button chip,boolean active) {
        chip.setBackground(chipBackground(active));chip.setPadding(dp(14),0,dp(14),0);
        chip.setTextColor(active?ON_ACCENT:MUTED);chip.setTypeface(Typeface.DEFAULT,active?Typeface.BOLD:Typeface.NORMAL);chip.setSelected(active);
    }
    private Button chip(ViewGroup parent,String label,Runnable action) {
        Button chip=new Button(this);flatten(chip);chip.setText(label);chip.setAllCaps(false);chip.setTextSize(14);
        chip.setMinHeight(dp(48));chip.setMinimumHeight(dp(48));chip.setMinWidth(0);chip.setMinimumWidth(0);chipStyle(chip,false);
        parent.addView(chip);chip.setOnClickListener(v->{if(!busy)action.run();});chip.setEnabled(!busy);buttons.add(chip);return chip;
    }
    /** "● 온라인" / "● 연결 끊김" pill for the Pi connection. */
    private TextView statusChip(LinearLayout parent,boolean online) {
        TextView chip=new TextView(this);chip.setText(online?"● 온라인":"● 연결 끊김");chip.setTextSize(12);chip.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        chip.setTextColor(online?ONLINE:DANGER);chip.setBackground(shape(online?ONLINE_SURFACE:DANGER_SURFACE,14));
        chip.setPadding(dp(10),dp(5),dp(10),dp(5));chip.setContentDescription(online?"Pi 연결됨":"Pi 연결 끊김");chip.setSingleLine();
        parent.addView(chip,new LinearLayout.LayoutParams(-2,-2));return chip;
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
        screenKey=viewMode+":"+(currentHome==null ? "" : currentHome)+":"+routeArg;
        final int y=scrollPositions.getOrDefault(screenKey,0);
        buttons.clear();
        pushStatus=null;pushDetail=null;pushReceipt=null;pushToggle=null;headerTitle=null;headerSubtitle=null;bellBadge=null;bellButton=null;
        shell=new LinearLayout(this); shell.setOrientation(LinearLayout.VERTICAL); shell.setBackgroundColor(BACKGROUND); shell.setTag("family_shell");
        // The bottom inset gets its own strip so the navigation surface continues under the system bar.
        final View bottomInset=new View(this);
        shell.setOnApplyWindowInsetsListener((view,insets)-> {
            view.setPadding(0,insets.getSystemWindowInsetTop(),0,0);
            ViewGroup.LayoutParams p=bottomInset.getLayoutParams();int height=insets.getSystemWindowInsetBottom();
            if(p!=null && p.height!=height){p.height=height;bottomInset.setLayoutParams(p);}
            return insets;
        });
        LinearLayout bar=new LinearLayout(this);bar.setGravity(Gravity.CENTER_VERTICAL);bar.setPadding(dp(8),dp(8),dp(8),dp(8));bar.setMinimumHeight(dp(64));
        boolean detail=inHome(viewMode) && !tabMode(viewMode);
        if(detail) iconButton(bar,"back","뒤로",this::back);
        if(viewMode.equals("home")) {
            // The home name opens the switcher (other homes, 새 집 만들기, 가족 초대 수락).
            Button name=new Button(this);flatten(name);name.setAllCaps(false);name.setText(title);name.setTextSize(22);name.setTextColor(INK);
            name.setTypeface(Typeface.DEFAULT,Typeface.BOLD);name.setSingleLine();name.setEllipsize(TextUtils.TruncateAt.END);
            name.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);name.setBackground(ripple(Color.TRANSPARENT,14));
            name.setCompoundDrawables(null,null,new FamilyIcon("expand",MUTED,dp(20)),null);name.setCompoundDrawablePadding(dp(6));
            name.setPadding(dp(8),0,dp(8),0);name.setMinHeight(dp(48));name.setMinimumHeight(dp(48));name.setMinWidth(0);name.setMinimumWidth(0);
            name.setOnClickListener(v->{if(!busy)homeSwitcher();});name.setEnabled(!busy);buttons.add(name);name.setTag("family_home_switcher");
            name.setAccessibilityDelegate(new View.AccessibilityDelegate() {
                @Override public void onInitializeAccessibilityNodeInfo(View host,AccessibilityNodeInfo info) {
                    super.onInitializeAccessibilityNodeInfo(host,info);info.setHintText("집 바꾸기");
                }
            });
            // The holder bounds the width so a long name ellipsizes and the chevron stays next to it.
            LinearLayout holder=new LinearLayout(this);holder.setGravity(Gravity.CENTER_VERTICAL);
            bar.addView(holder,new LinearLayout.LayoutParams(0,-2,1));holder.addView(name,new LinearLayout.LayoutParams(-2,-2));
            headerTitle=name;
        } else {
            LinearLayout titles=new LinearLayout(this);titles.setOrientation(LinearLayout.VERTICAL);titles.setPadding(dp(detail?4:12),0,0,0);
            bar.addView(titles,new LinearLayout.LayoutParams(0,-2,1));
            headerTitle=text(titles,title,detail?20:22,INK,true);headerTitle.setSingleLine();headerTitle.setEllipsize(TextUtils.TruncateAt.END);
            headerSubtitle=text(titles,subtitle,13,MUTED,false);headerSubtitle.setVisibility(subtitle.isEmpty()?View.GONE:View.VISIBLE);
        }
        if(viewMode.equals("home")) { iconButton(bar,"refresh","집 새로고침",this::refreshHome); bell(bar); }
        else if(viewMode.equals("alerts")) iconButton(bar,"refresh","알림 새로고침",this::refreshHome);
        else if(viewMode.equals("device") || viewMode.equals("aircon")) favoriteButton(bar,routeArg);
        shell.addView(bar); divider(shell);
        scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setTag("family_scroll");
        scroll.setClipToPadding(false);scroll.setDescendantFocusability(android.view.ViewGroup.FOCUS_BEFORE_DESCENDANTS);
        scroll.setFocusableInTouchMode(true);
        page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),dp(14),dp(20),dp(24));
        scroll.addView(page);shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        footer=new LinearLayout(this);footer.setOrientation(LinearLayout.VERTICAL);shell.addView(footer);
        if(BuildConfig.FLAVOR.equals("fixture")) text(page,"동작 시험 · 가상 계정",12,WARNING,true);
        boolean nav=session!=null && session.userId()!=null && tabMode(viewMode);
        if(nav) navigationBar();
        bottomInset.setBackgroundColor(nav?SURFACE:BACKGROUND);shell.addView(bottomInset,new LinearLayout.LayoutParams(-1,0));
        setContentView(shell);restoreScroll(y);
        refreshHeader();
    }
    private void replacePage(Runnable render) {
        if(page==null || scroll==null) return;
        int y=scroll.getScrollY();
        page.removeAllViews();buttons.removeIf(b->!insideShell(b));
        if(BuildConfig.FLAVOR.equals("fixture")) text(page,"동작 시험 · 가상 계정",12,WARNING,true);
        render.run();restoreScroll(y);
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
        value.setBackground(shape(SURFACE,18));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2); params.bottomMargin=dp(12); page.addView(value,params); return value;
    }
    /** Primary: accent pill. Secondary: raised surface. Use {@link #danger(Button)} for destructive actions. */
    private Button button(LinearLayout parent,String label,boolean primary,Runnable action) {
        Button view=new Button(this); flatten(view);view.setText(label); view.setAllCaps(false); view.setTextSize(15);
        if(primary){view.setTextColor(ON_ACCENT);view.setTypeface(Typeface.DEFAULT,Typeface.BOLD);view.setBackground(ripple(ACCENT,24));view.setMinHeight(dp(52));view.setMinimumHeight(dp(52));}
        else{view.setTextColor(INK);view.setBackground(ripple(RAISED,14));view.setMinHeight(dp(48));}
        view.setPadding(dp(16),dp(8),dp(16),dp(8));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2); params.topMargin=dp(10); parent.addView(view,params);
        view.setEnabled(!busy); view.setOnClickListener(v -> { if (!busy) action.run(); }); buttons.add(view); return view;
    }
    private Button danger(Button button) {
        button.setTextColor(DANGER);button.setBackground(ripple(DANGER_SURFACE,14));button.setPadding(dp(16),dp(8),dp(16),dp(8));return button;
    }
    /** Round, text-less button whose meaning comes from its content description. */
    private Button roundButton(LinearLayout parent,String icon,int fill,int iconColor,int size,String label,Runnable action) {
        Button button=new Button(this);flatten(button);button.setContentDescription(label);
        button.setBackground(circleIcon(icon,fill,iconColor,size,size>=52?24:size>=44?22:18));button.setPadding(0,0,0,0);
        button.setMinWidth(0);button.setMinimumWidth(0);button.setMinHeight(0);button.setMinimumHeight(0);
        parent.addView(button,new LinearLayout.LayoutParams(dp(size),dp(size)));
        button.setOnClickListener(v->{if(!busy)action.run();});return button;
    }
    private Button iconButton(LinearLayout parent,String icon,String label,Runnable action) {
        Button button=new Button(this);flatten(button);button.setContentDescription(label);button.setBackground(ripple(Color.TRANSPARENT,24));
        button.setCompoundDrawables(null,new FamilyIcon(icon,INK,dp(22)),null,null);button.setPadding(dp(12),dp(12),dp(12),dp(12));
        parent.addView(button,new LinearLayout.LayoutParams(dp(48),dp(48)));button.setOnClickListener(v->{if(!busy)action.run();});
        button.setEnabled(!busy);buttons.add(button);return button;
    }
    /** Bell with a badge counting the 지금 확인할 것 items; opens the 알림 tab. */
    private void bell(LinearLayout bar) {
        FrameLayout frame=new FrameLayout(this);bar.addView(frame,new LinearLayout.LayoutParams(dp(48),dp(48)));
        Button button=new Button(this);flatten(button);button.setBackground(ripple(Color.TRANSPARENT,24));button.setContentDescription("알림");
        button.setCompoundDrawables(null,new FamilyIcon("bell",INK,dp(22)),null,null);button.setPadding(dp(12),dp(12),dp(12),dp(12));
        button.setOnClickListener(v->{if(!busy)tab("alerts");});button.setEnabled(!busy);buttons.add(button);
        frame.addView(button,new FrameLayout.LayoutParams(-1,-1));
        TextView count=new TextView(this);count.setTextSize(10);count.setTextColor(BACKGROUND);count.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        count.setGravity(Gravity.CENTER);count.setBackground(shape(DANGER,9));count.setPadding(dp(4),0,dp(4),0);count.setMinWidth(dp(18));
        count.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);count.setVisibility(View.GONE);
        FrameLayout.LayoutParams p=new FrameLayout.LayoutParams(-2,dp(18),Gravity.TOP|Gravity.END);p.topMargin=dp(5);p.rightMargin=dp(3);
        frame.addView(count,p);bellBadge=count;bellButton=button;
    }
    private void favoriteButton(LinearLayout bar,String id) {
        Button star=new Button(this);flatten(star);star.setBackground(ripple(Color.TRANSPARENT,24));star.setPadding(dp(12),dp(12),dp(12),dp(12));
        Runnable style=()->{
            boolean on=favorite(id);
            star.setCompoundDrawables(null,new FamilyIcon(on?"star_filled":"star",on?WARNING:INK,dp(22)),null,null);
            star.setContentDescription(on?"즐겨찾기에서 빼기":"즐겨찾기에 추가");
        };
        style.run();
        star.setOnClickListener(v->{if(busy)return;toggleFavorite(id);style.run();});
        bar.addView(star,new LinearLayout.LayoutParams(dp(48),dp(48)));
    }
    private void divider(LinearLayout parent) {
        View line=new View(this);line.setBackgroundColor(LINE);parent.addView(line,new LinearLayout.LayoutParams(-1,dp(1)));
    }
    private void gap(LinearLayout parent,int height) { parent.addView(new View(this),new LinearLayout.LayoutParams(1,dp(height))); }
    private TextView section(String label) {
        TextView view=text(page,label,13,MUTED,true);view.setPadding(dp(4),dp(8),0,dp(6));return view;
    }
    private Button row(LinearLayout parent,String icon,String label,String description,Runnable action) {
        Button row=new Button(this);flatten(row);row.setText(label+(description.isEmpty()?"":"\n"+description));row.setAllCaps(false);row.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);
        row.setTextSize(15);row.setTextColor(INK);row.setBackground(ripple(Color.TRANSPARENT,12));
        row.setCompoundDrawables(new FamilyIcon(icon,ACCENT,dp(22)),null,new FamilyIcon("chevron",MUTED,dp(18)),null);
        row.setCompoundDrawablePadding(dp(14));row.setPadding(dp(8),dp(14),dp(8),dp(14));row.setMinHeight(dp(56));
        parent.addView(row,new LinearLayout.LayoutParams(-1,-2));row.setOnClickListener(v->{if(!busy)action.run();});row.setEnabled(!busy);buttons.add(row);return row;
    }
    /** Label (and caption) on the left, the current value in accent on the right; used for the level and time rows. */
    private LinearLayout valueRow(LinearLayout parent,String label,String caption,String value,Runnable action) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(8),dp(8),dp(4),dp(8));row.setMinimumHeight(dp(56));
        row.setBackground(ripple(Color.TRANSPARENT,12));row.setClickable(true);row.setFocusable(true);asButton(row);
        LinearLayout texts=new LinearLayout(this);texts.setOrientation(LinearLayout.VERTICAL);row.addView(texts,new LinearLayout.LayoutParams(0,-2,1));
        text(texts,label,15,INK,false);if(!caption.isEmpty())text(texts,caption,12,MUTED,false);
        TextView current=text(row,value,14,ACCENT,true);current.setPadding(dp(8),0,dp(6),0);
        icon(row,"chevron",MUTED,18);
        row.setOnClickListener(v->{if(!busy)action.run();});
        parent.addView(row,new LinearLayout.LayoutParams(-1,-2));return row;
    }
    /** Active tab: accent icon and label over a raised pill indicator behind the icon. */
    private Drawable navBackground(boolean active) {
        LayerDrawable layers=new LayerDrawable(new Drawable[]{shape(active?RAISED:Color.TRANSPARENT,16)});
        layers.setLayerGravity(0,Gravity.TOP|Gravity.CENTER_HORIZONTAL);layers.setLayerSize(0,dp(60),dp(32));layers.setLayerInsetTop(0,dp(1));
        return new RippleDrawable(ColorStateList.valueOf(RIPPLE_LIGHT),layers,shape(INK,16));
    }
    private void navigationBar() {
        divider(shell);
        LinearLayout nav=new LinearLayout(this);nav.setBackgroundColor(SURFACE);nav.setPadding(dp(10),dp(6),dp(10),dp(6));
        String[] labels={"홈","알림","설정"}, icons={"home","bell","settings"}, modes={"home","alerts","settings"};
        for(int i=0;i<labels.length;i++) {
            final String mode=modes[i];Button item=new Button(this);flatten(item);final boolean active=mode.equals(viewMode);
            item.setText(labels[i]);item.setTextSize(12);item.setAllCaps(false);item.setTextColor(active?ACCENT:MUTED);
            if(active)item.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
            item.setCompoundDrawables(null,new FamilyIcon(icons[i],active?ACCENT:MUTED,dp(22)),null,null);
            item.setBackground(navBackground(active));item.setCompoundDrawablePadding(dp(6));item.setPadding(0,dp(6),0,dp(4));
            item.setSelected(active);item.setOnClickListener(v->{if(!busy && !active)tab(mode);});item.setEnabled(!busy);buttons.add(item);
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(62),1);p.setMargins(dp(5),0,dp(5),0);nav.addView(item,p);
        }
        shell.addView(nav);
    }
    /** Footer pinned under the scroll area. */
    private LinearLayout pinnedFooter() {
        footer.removeAllViews();footer.setBackgroundColor(BACKGROUND);footer.setPadding(0,0,0,0);divider(footer);
        LinearLayout inner=new LinearLayout(this);inner.setOrientation(LinearLayout.VERTICAL);inner.setPadding(dp(20),dp(10),dp(20),dp(12));
        footer.addView(inner,new LinearLayout.LayoutParams(-1,-2));return inner;
    }
    private void flatten(Button button) {button.setStateListAnimator(null);button.setElevation(0);}
    private void working(boolean value) { busy=value; for (Button button:buttons) button.setEnabled(!value && !"aircon-disabled".equals(button.getTag())); }
    private void message(String value) { Toast.makeText(this,value,Toast.LENGTH_LONG).show(); }
    private static String role(String value) { return value.equals("owner") ? "소유자" : value.equals("member") ? "가족" : "조회 전용"; }
    private boolean owner() { return currentHouse!=null && "owner".equals(currentHouse.optString("role")); }
    /** Two lines in one label: the second smaller and muted. */
    private CharSequence twoLines(String first,String second) {
        SpannableStringBuilder value=new SpannableStringBuilder(first);
        if(second.isEmpty()) return value;
        value.append('\n');int start=value.length();value.append(second);
        value.setSpan(new RelativeSizeSpan(.85f),start,value.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        value.setSpan(new ForegroundColorSpan(MUTED),start,value.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        return value;
    }
    private JSONObject json(String... fields) {
        JSONObject object=new JSONObject();
        try { for (int index=0;index<fields.length;index+=2) object.put(fields[index],fields[index+1]); }
        catch(JSONException ignored) { throw new IllegalArgumentException(); }
        return object;
    }
    /** Reports a tappable container as a button to TalkBack (its selected state is read as well). */
    private void asButton(View view) {
        view.setAccessibilityDelegate(new View.AccessibilityDelegate() {
            @Override public void onInitializeAccessibilityNodeInfo(View host,AccessibilityNodeInfo info) {
                super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName(Button.class.getName());
            }
        });
    }

    // ---- Sign-in, connection and server trust ----

    private void loginPage() {
        viewMode="login";routeArg="";backStack.clear();
        currentHome=null; userId=null; homeList.reset();clearHomeData();scrollPositions.clear();
        screen("가족 스마트홈", "");
        gap(page,30);
        badge(page,"home",RAISED,ACCENT,72,36);
        gap(page,20);text(page,"우리 집을 함께",26,INK,true);text(page,"가족만 연결되는 나의 스마트홈",15,ACCENT,true);gap(page,14);
        text(page,"문이 열릴 때, 집에 변화가 있을 때.\n어디서든 우리 집 소식을 받아보세요.",17,MUTED,false);gap(page,24);
        LinearLayout intro=card();
        text(intro,"같은 집, 각자의 계정",18,INK,true);
        text(intro,"내 집을 만들거나 가족의 초대를 받아 시작해요.",14,MUTED,false);
        button(intro,"Google로 계속하기",true,()-> {
            working(true); int epoch=generation;
            session.signIn(()-> { if(epoch==generation && !isDestroyed()){ working(false); if(endpoint.isEmpty()) connectionPage(); else start(); } },error -> {
                if(epoch==generation && !isDestroyed()){ working(false); message(error); }
            });
        });
        button(page,"연결 설정",false,this::connectionSettings);
        gap(page,16);text(page,"집 소유자가 초대한 가족만 참여할 수 있어요.",13,MUTED,false);
    }
    private void connectionPage() {
        viewMode="connection";routeArg="";
        screen("로그인됐어요", "우리 집 서버를 연결해 주세요.");
        LinearLayout info=card();
        badge(info,"network",RAISED,ACCENT,48,24);gap(info,10);
        text(info,"우리 집 연결 주소",20,INK,true);
        text(info,"집 소유자가 안내한 주소를 입력하면 가족과 집 목록을 확인할 수 있어요.",15,MUTED,false);
        gap(info,8);divider(info);fingerprintNote(info);
        button(info,"연결 설정",true,this::connectionSettings);
        button(page,"로그아웃",false,this::logout);
    }
    private void connectionSettings() {
        EditText input=new EditText(this); input.setSingleLine(); input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(endpoint); input.setHint("https://집에서 안내받은 주소");
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("우리 집 연결 주소").setMessage("소유자가 안내한 중앙 서버 주소를 입력해 주세요. 주소가 바뀌어도 저장된 서버 지문은 그대로예요.")
            .setView(input).setNegativeButton("취소",null).setPositiveButton("저장",null).create();
        dialog.setOnShowListener(unused -> dialog.getButton(-1).setOnClickListener(view -> {
            try {
                String selected=EndpointPolicy.validate(input.getText().toString(),BuildConfig.DEBUG);
                if (!endpoint.isEmpty() && !endpoint.equals(selected) && session.userId()!=null) { PushManager.disable(this); session.signOut(); }
                generation++; working(false); endpoint=selected;
                getPreferences(0).edit().putString("endpoint",endpoint).apply(); dialog.dismiss();
                if(session.userId()!=null) start(); else loginPage();
            } catch (IllegalArgumentException error) { input.setError(error.getMessage()); }
        })); dialog.show();
    }
    private void logout() { generation++; PushManager.disable(this); session.signOut(); working(false); loginPage(); }
    /** The pin taken at first contact; the owner compares it with the fingerprint the server prints. */
    private void fingerprintNote(LinearLayout parent) {
        String pin=ServerTrust.pinned(this);
        LinearLayout line=new LinearLayout(this);line.setPadding(dp(8),dp(12),dp(8),dp(8));parent.addView(line,new LinearLayout.LayoutParams(-1,-2));
        View icon=new View(this);icon.setBackground(new FamilyIcon("shield",ACCENT,dp(22)));icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(dp(22),dp(22));ip.topMargin=dp(3);ip.rightMargin=dp(14);line.addView(icon,ip);
        LinearLayout texts=new LinearLayout(this);texts.setOrientation(LinearLayout.VERTICAL);line.addView(texts,new LinearLayout.LayoutParams(0,-2,1));
        text(texts,"서버 지문 · "+(pin.isEmpty()?"아직 확인 전":ServerIdentity.display(pin)),13,INK,true);
        text(texts,pin.isEmpty()?"처음 연결할 때 서버 지문을 저장해요.":"처음 연결할 때 저장한 지문이에요. 소유자가 서버에서 출력한 지문과 같은지 비교해 주세요.",12,MUTED,false);
    }
    /** A verified server that is not the pinned one is accepted only here; cancelling keeps the old pin and no token was sent. */
    private void identityChanged(ServerTrust.Changed changed) {
        if(identityDialog!=null && identityDialog.isShowing()) return;
        identityDialog=new AlertDialog.Builder(this).setTitle("서버 신원이 바뀌었어요")
            .setMessage("주소를 보낸 사람이 소유자인지 확인하세요.\n\n저장된 지문 · "+ServerIdentity.display(ServerTrust.pinned(this))+"\n새 지문 · "+ServerIdentity.display(changed.fingerprint))
            .setNegativeButton("취소",null).setPositiveButton("이 서버로 바꾸기",(dialog,which)->{
                ServerTrust.repin(this,changed.fingerprint); generation++; working(false);
                if(session.userId()!=null) start(); else loginPage();
            }).show();
    }
    private void request(String method,String path,JSONObject value,Consumer<JSONObject> success) {
        request(method,path,value,success,null);
    }
    private void request(String method,String path,JSONObject value,Consumer<JSONObject> success,Consumer<String> onFailure) {
        BiConsumer<String,Exception> failed=onFailure==null ? null : (detail,failure)->onFailure.accept(detail);
        request(method,path,value,success,failed,false);
    }
    /** Quiet requests (refreshes and result checks) never touch busy, so the screen stays usable while they run. */
    private void request(String method,String path,JSONObject value,Consumer<JSONObject> success,BiConsumer<String,Exception> onFailure,boolean quiet) {
        final String account=session.userId();
        if(account==null){ logout(); return; }
        if(!quiet) working(true); final int epoch=generation; final String origin=endpoint;
        session.token((token,error)-> {
            if(stale(epoch,account,quiet)) return;
            if(error!=null){ if(!quiet) working(false); if(onFailure!=null)onFailure.accept("로그인을 다시 확인해 주세요.",error);else message("로그인을 다시 확인해 주세요."); return; }
            network.execute(()-> {
                try {
                    JSONObject reply=new ApiClient(this,origin,BuildConfig.DEBUG).request(token,method,path,value);
                    if(method.equals("GET") && path.equals("/v1/me") &&
                            (reply.optJSONArray("homes")==null || reply.optString("user_id").isEmpty()))
                        throw new ApiClient.Failure(200,"invalid_response");
                    runOnUiThread(()-> {
                        if(stale(epoch,account,quiet)) return;
                        if(!quiet) working(false); success.accept(reply);
                    });
                } catch(Exception failure){ runOnUiThread(()-> {
                    if(stale(epoch,account,quiet)) return;
                    if(!quiet) working(false);
                    String detail=ApiErrorMessages.describe(failure);
                    if(failure instanceof ServerTrust.Changed) identityChanged((ServerTrust.Changed)failure);
                    if(onFailure!=null){ onFailure.accept(detail,failure); return; }
                    if(failure instanceof ServerTrust.Changed) return;
                    if(failure instanceof ApiClient.Failure){
                        ApiClient.Failure f=(ApiClient.Failure)failure;
                        if(f.status==409 && f.code.equals("installation_not_registered")) {
                            PushManager.sync(this);
                            notificationHelp("이 휴대폰의 알림을 연결해 주세요",detail);
                            return;
                        }
                        if(homeGone(failure)){ leaveHome(); message(detail); return; }
                    }
                    message(detail);
                }); }
            });
        });
    }
    /** Drops callbacks from an older screen; a foreground sign-out (disabled or revoked account) returns to login instead of leaving busy set. */
    private boolean stale(int epoch,String account,boolean quiet) {
        if(epoch!=generation || isDestroyed()) return true;
        if(account.equals(session.userId())) return false;
        if(!quiet) working(false); if(session.userId()==null) logout(); return true;
    }
    /** The household no longer lists this account (left, revoked or deleted): the server answers 404 not_found. */
    private boolean homeGone(Exception failure) {
        return currentHome!=null && failure instanceof ApiClient.Failure && !(failure instanceof ServerTrust.Changed)
            && ((ApiClient.Failure)failure).status==404 && "not_found".equals(((ApiClient.Failure)failure).code);
    }

    // ---- Start: last-used home, onboarding and the home switcher ----

    private String lastHomeKey() { return "last_home:"+(session.userId()==null ? "" : session.userId()); }
    private void rememberHome(String id) { getPreferences(0).edit().putString(lastHomeKey(),id).apply(); }
    private void forgetHome(String id) {
        if(id!=null && id.equals(getPreferences(0).getString(lastHomeKey(),""))) getPreferences(0).edit().remove(lastHomeKey()).apply();
    }
    private void clearHomeData() {
        currentHouse=null;homeError=null;events=new ArrayList<>();eventsLoaded=false;eventsError=null;serverInventory=null;devicesLoaded=false;
        aircon=null;airconLoaded=false;airconError=null;selectedAircon=null;airconDrafts.clear();eventFilter="all";expanded.clear();
    }
    /** After sign-in: open the last-used home directly (or the first), or onboarding when there is none. */
    private void start() {
        viewMode="start";routeArg="";backStack.clear();
        PushManager.sync(this);
        generation++; currentHome=null; clearHomeData(); working(false);
        screen("가족 스마트홈","");
        homeList.begin();
        renderStart();
        request("GET","/v1/me",null,result -> {
            userId=result.optString("user_id");
            JSONArray list=result.optJSONArray("homes");
            homeList.succeed(list,list.length());
            if(list.length()==0){ onboarding(); return; }
            String last=getPreferences(0).getString(lastHomeKey(),""), chosen=null;
            for(int i=0;i<list.length();i++){ JSONObject house=list.optJSONObject(i); if(house!=null && last.equals(house.optString("id"))) chosen=last; }
            if(chosen==null){ JSONObject first=list.optJSONObject(0); chosen=first==null ? "" : first.optString("id"); }
            if(chosen.isEmpty()){ onboarding(); return; }
            enterHome(chosen);
        },detail -> {
            homeList.fail(detail);
            replacePage(this::renderStart);
        });
    }
    private void renderStart() {
        HomeListState.Status status=homeList.status();
        if(status==HomeListState.Status.LOADING) {
            LinearLayout loading=card();text(loading,"우리 집을 불러오고 있어요…",17,INK,true);
            return;
        }
        if(status==HomeListState.Status.UNAVAILABLE || status==HomeListState.Status.STALE) {
            LinearLayout unavailable=card();TextView failed=text(unavailable,"집 목록을 불러오지 못했어요",19,INK,true);
            failed.setCompoundDrawables(new FamilyIcon("warning",WARNING,dp(20)),null,null,null);failed.setCompoundDrawablePadding(dp(10));
            text(unavailable,homeList.error(),14,MUTED,false);
            if(endpoint.contains(".trycloudflare.com"))
                text(unavailable,"임시 연결 주소는 서버가 다시 켜지면 바뀔 수 있어요. 집 소유자에게 현재 주소를 확인해 주세요.",14,MUTED,false);
            button(unavailable,"다시 연결",true,this::start);
            button(unavailable,"연결 설정",false,this::connectionSettings);
        }
        JSONArray list=homeList.snapshot();
        if(list.length()>0) {
            section(status==HomeListState.Status.STALE?"마지막으로 확인한 집":"참여한 집");
            LinearLayout houses=card();houses.setPadding(dp(8),dp(4),dp(8),dp(4));
            for(int i=0;i<list.length();i++) {
                JSONObject house=list.optJSONObject(i);if(house==null)continue;
                if(i>0)divider(houses);
                final String id=house.optString("id");
                row(houses,"home",house.optString("name"),role(house.optString("role")),()->enterHome(id));
            }
        }
        row(page,"logout","로그아웃","",this::logout);
    }
    private void onboarding() {
        viewMode="onboarding";routeArg="";backStack.clear();generation++;working(false);
        screen("우리 집 시작하기","");
        gap(page,12);badge(page,"home",RAISED,ACCENT,64,32);gap(page,14);
        text(page,"아직 연결된 집이 없어요",22,INK,true);
        text(page,"새 집을 만들거나 가족이 보낸 초대를 수락해 주세요.",15,MUTED,false);gap(page,8);
        button(page,"새 집 만들기",true,this::createHome);
        gap(page,8);LinearLayout more=card();more.setPadding(dp(8),dp(4),dp(8),dp(4));
        row(more,"family","가족 초대 수락","",this::acceptInvitation);divider(more);
        row(more,"network","연결 설정","",this::connectionSettings);divider(more);
        row(more,"logout","로그아웃","",this::logout);
    }
    private void enterHome(String id) {
        if(id==null || id.isEmpty()){ start(); return; }
        if(!id.equals(currentHome)) clearHomeData();
        currentHome=id; rememberHome(id); tab("home");
    }
    /** Membership lost: forget it as the last-used home and pick again from the server's list. */
    private void leaveHome() { forgetHome(currentHome); currentHome=null; clearHomeData(); start(); }
    private void homeSwitcher() {
        if(switcherDialog!=null && switcherDialog.isShowing()) return;
        homeList.begin();
        request("GET","/v1/me",null,result -> {
            userId=result.optString("user_id");
            JSONArray list=result.optJSONArray("homes");homeList.succeed(list,list.length());showSwitcher();
        },detail -> { homeList.fail(detail); if(homeList.count()>0) showSwitcher(); else message(detail); });
    }
    private void showSwitcher() {
        if(isDestroyed() || (switcherDialog!=null && switcherDialog.isShowing())) return;
        JSONArray list=homeList.snapshot();
        ScrollView holder=new ScrollView(this);LinearLayout content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(12),dp(8),dp(12),dp(4));holder.addView(content);
        final AlertDialog[] dialog=new AlertDialog[1];
        for(int i=0;i<list.length();i++) {
            JSONObject house=list.optJSONObject(i);if(house==null)continue;
            final String id=house.optString("id");
            dialogRow(content,"home",twoLines(house.optString("name"),role(house.optString("role"))),id.equals(currentHome),()->{
                dialog[0].dismiss(); if(!id.equals(currentHome)) enterHome(id);
            });
        }
        divider(content);
        dialogRow(content,"add","새 집 만들기",false,()->{dialog[0].dismiss();createHome();});
        dialogRow(content,"family","가족 초대 수락",false,()->{dialog[0].dismiss();acceptInvitation();});
        dialog[0]=switcherDialog=new AlertDialog.Builder(this).setTitle("집 바꾸기").setView(holder).setNegativeButton("닫기",null).show();
    }
    private void dialogRow(LinearLayout parent,String icon,CharSequence label,boolean current,Runnable action) {
        Button row=new Button(this);flatten(row);row.setText(label);row.setAllCaps(false);row.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);
        row.setTextSize(15);row.setTextColor(INK);row.setBackground(ripple(Color.TRANSPARENT,12));
        row.setCompoundDrawables(new FamilyIcon(icon,ACCENT,dp(22)),null,current?new FamilyIcon("check",ACCENT,dp(20)):null,null);
        row.setCompoundDrawablePadding(dp(14));row.setPadding(dp(8),dp(12),dp(8),dp(12));row.setMinHeight(dp(56));row.setSelected(current);
        parent.addView(row,new LinearLayout.LayoutParams(-1,-2));row.setOnClickListener(v->action.run());
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
    private void createHome() { singleInput("새 집 만들기","예: 우리 집",80,name -> request("POST","/v1/homes",json("name",name),reply -> enterHome(reply.optString("id")))); }
    private void acceptInvitation(){ singleInput("가족 초대 수락","가족에게 받은 초대 코드",128,token -> request("POST","/v1/invitations/accept",json("invitation_token",token),reply -> enterHome(reply.optString("home_id")))); }

    // ---- Home data: house, devices, records and aircon status ----

    private double now() { return System.currentTimeMillis()/1000.0; }
    private ControlStatus control() { return aircon==null ? null : ControlStatus.from(JsonValues.map(aircon)); }
    /** The fallback list needs the aircon control list, so it waits for that answer. */
    private boolean devicesReady() {
        if(!devicesLoaded) return false;
        if(serverInventory!=null && !serverInventory.neverReported()) return true;
        return airconLoaded;
    }
    private Inventory inventory() { return Inventory.effective(serverInventory,control(),events); }
    private List<Attention.Item> attention() {
        return devicesReady() ? Attention.compute(inventory(),events,control(),now()) : new ArrayList<>();
    }
    /** Loads house → devices → records → aircon status; each answer redraws the open screen. Refreshes are quiet once the home is known. */
    private void syncHome() { syncHome(currentHouse!=null); }
    private void refreshHome() { generation++; working(false); syncHome(false); }
    private void syncHome(boolean quiet) {
        if(currentHome==null) return;
        final String home=currentHome;
        request("GET","/v1/homes/"+home,null,house -> {
            currentHouse=house;homeError=null;
            if(viewMode.equals("settings")){ refreshHeader(); replacePage(this::renderSettings); } else refreshView();
            loadDevices(home,quiet);
        },(detail,failure) -> {
            if(failure instanceof ServerTrust.Changed) return;
            if(homeGone(failure)){ leaveHome(); message(detail); return; }
            if(!quiet) message(detail);
            if(currentHouse==null){ homeError=detail; refreshView(); }
        },quiet);
    }
    private void loadDevices(String home,boolean quiet) {
        request("GET","/v1/homes/"+home+"/devices",null,reply -> {
            serverInventory=Inventory.from(JsonValues.map(reply));devicesLoaded=true;refreshView();
            loadEvents(home,quiet);
        },(detail,failure) -> {
            if(failure instanceof ServerTrust.Changed) return;
            // 404: a server older than 0.7 has no device list; the screens build one from the control list and records.
            boolean older=failure instanceof ApiClient.Failure && ((ApiClient.Failure)failure).status==404;
            serverInventory=null;devicesLoaded=true;
            if(!older && !quiet) message(detail);
            refreshView();loadEvents(home,quiet);
        },quiet);
    }
    private void loadEvents(String home,boolean quiet) {
        request("GET","/v1/homes/"+home+"/events",null,reply -> {
            events=AppEvent.list(JsonValues.list(reply.optJSONArray("events")));eventsLoaded=true;eventsError=null;refreshView();
            loadAircon(quiet);
        },(detail,failure) -> {
            if(failure instanceof ServerTrust.Changed) return;
            if(homeGone(failure)){ leaveHome(); message(detail); return; }
            eventsError=detail;if(!quiet) message(detail);
            refreshView();loadAircon(quiet);
        },quiet);
    }
    private void loadAircon() { loadAircon(false); }
    private void loadAircon(boolean quiet) {
        if(currentHome==null || !inHome(viewMode))return;
        final String home=currentHome;
        request("GET","/v1/homes/"+home+"/control",null,reply->{
            aircon=reply;airconLoaded=true;airconError=null;
            refreshAirconView();
            JSONObject command=aircon.optJSONObject("latest_command");
            if(command!=null && AirconUi.pending(command.optString("state")))
                pollAircon(home,command.optString("id"),generation,0);
        },(detail,failure)->{
            if(failure instanceof ServerTrust.Changed) return;
            airconLoaded=true;airconError=detail;refreshAirconView();
        },quiet);
    }
    /** Redraws the open screen from the data in memory, keeping its scroll position. */
    private void refreshView() {
        if(isDestroyed() || page==null) return;
        refreshHeader();
        switch(viewMode) {
            case "home": replacePage(this::renderHome); break;
            case "alerts": replacePage(this::renderAlerts); break;
            case "category": replacePage(this::renderCategory); break;
            case "device": replacePage(this::renderDevice); break;
            default: break;
        }
    }
    private void refreshAirconView() {
        if(viewMode.equals("aircon")){ refreshHeader(); replacePage(this::renderAirconControls); }
        else refreshView();
    }
    private void refreshHeader() {
        if(headerTitle==null || !inHome(viewMode)) return;
        String[] titles=titles();
        headerTitle.setText(titles[0]);
        if(headerSubtitle!=null){ headerSubtitle.setText(titles[1]); headerSubtitle.setVisibility(titles[1].isEmpty()?View.GONE:View.VISIBLE); }
        if(bellBadge!=null) {
            int count=attention().size();
            bellBadge.setText(count>99 ? "99+" : String.valueOf(count));bellBadge.setVisibility(count>0?View.VISIBLE:View.GONE);
            bellButton.setContentDescription(count>0 ? "알림, 확인할 것 "+count+"개" : "알림");
        }
    }
    private String[] titles() {
        switch(viewMode) {
            case "home": return new String[]{currentHouse==null ? "우리 집" : currentHouse.optString("name"),""};
            case "alerts": return new String[]{"알림",""};
            case "settings": return new String[]{"설정",""};
            case "members": return new String[]{"가족 관리",currentHouse==null ? "" : currentHouse.optString("name")};
            case "category": return new String[]{DeviceCategory.label(routeArg),devicesReady() ? DeviceText.category(routeArg,inventory().devices,now()) : ""};
            case "device": case "aircon": {
                Device device=devicesReady() ? inventory().find(routeArg) : null;
                if(device!=null) return new String[]{device.name,device.room};
                return new String[]{viewMode.equals("aircon") ? airconName(routeArg) : "기기",""};
            }
            default: return new String[]{"가족 스마트홈",""};
        }
    }
    private String airconName(String id) {
        Device device=devicesReady() ? inventory().find(id) : null;
        if(device!=null) return device.name;
        ControlStatus control=control();String name=control==null ? null : control.deviceName(id);
        return name==null ? "에어컨" : name;
    }

    // ---- Favorites (this phone only, per home) ----

    private String favoritesKey() { return "favorites:"+currentHome; }
    private Set<String> favoriteIds() { return new HashSet<>(getPreferences(0).getStringSet(favoritesKey(),Collections.emptySet())); }
    private boolean favorite(String id) { return favoriteIds().contains(id); }
    private void toggleFavorite(String id) {
        Set<String> ids=favoriteIds();boolean added=!ids.remove(id);if(added)ids.add(id);
        getPreferences(0).edit().putStringSet(favoritesKey(),ids).apply();
        message(added ? "즐겨찾기에 추가했어요." : "즐겨찾기에서 뺐어요.");
    }
    private List<Device> favorites(List<Device> devices) {
        Set<String> ids=favoriteIds();List<Device> result=new ArrayList<>();
        for(Device device:devices) if(ids.contains(device.id)) result.add(device);
        return result;
    }

    // ---- 홈 tab ----

    private void showHome() {
        if(currentHome==null){start();return;}
        viewMode="home";routeArg="";generation++;working(false);
        screen(titles()[0],"");renderHome();syncHome();
    }
    private void renderHome() {
        if(currentHouse==null){ homeLoading(); return; }
        if(!devicesReady()){ text(page,"기기를 확인하고 있어요…",14,MUTED,false); return; }
        double now=now();Inventory inventory=inventory();List<Device> devices=inventory.devices;
        List<Attention.Item> items=Attention.compute(inventory,events,control(),now);
        if(!items.isEmpty()){ section("지금 확인할 것"); attentionList(items); }
        if(devices.isEmpty()){
            LinearLayout empty=card();text(empty,"아직 연결된 기기가 없어요",16,INK,true);
            if(owner()) button(empty,"Pi 허브 연결",true,this::claimHub);
            return;
        }
        section("종류별 모아보기");categoryChips(devices,now);
        List<Device> favorites=favorites(devices);
        if(!favorites.isEmpty()){ section("즐겨찾기"); grid(page,favorites,now); gap(page,4); }
        for(Map.Entry<String,List<Device>> room:DeviceText.rooms(devices).entrySet()){
            roomHeader(page,room.getKey(),room.getValue());grid(page,room.getValue(),now);gap(page,4);
        }
    }
    private void homeLoading() {
        if(homeError==null){ text(page,"우리 집을 확인하고 있어요…",15,MUTED,false); return; }
        LinearLayout failed=card();text(failed,"우리 집을 불러오지 못했어요",17,INK,true);text(failed,homeError,14,MUTED,false);
        button(failed,"다시 연결",true,this::refreshHome);
        button(failed,"연결 설정",false,this::connectionSettings);
    }
    private String attentionIcon(Attention.Item item) {
        if(item.key.startsWith("door:")) return "door";
        if(item.key.startsWith("command:")) return "aircon";
        if(item.key.startsWith("automation:")) return "warning";
        if(item.key.startsWith("battery:")) return "battery";
        return "wifi_off";
    }
    private void attentionList(List<Attention.Item> items) {
        LinearLayout box=card();box.setPadding(dp(6),dp(4),dp(6),dp(4));
        for(int i=0;i<items.size();i++) {
            if(i>0) divider(box);
            final Attention.Item item=items.get(i);
            int tint=item.tone==Attention.Tone.DANGER?DANGER:item.tone==Attention.Tone.WARNING?WARNING:MUTED;
            int fill=item.tone==Attention.Tone.DANGER?DANGER_SURFACE:item.tone==Attention.Tone.WARNING?WARNING_SURFACE:RAISED;
            LinearLayout entry=new LinearLayout(this);entry.setGravity(Gravity.CENTER_VERTICAL);entry.setPadding(dp(10),dp(10),dp(8),dp(10));
            entry.setBackground(ripple(Color.TRANSPARENT,12));entry.setClickable(true);entry.setFocusable(true);asButton(entry);
            badge(entry,attentionIcon(item),fill,tint,36,18);
            LinearLayout texts=new LinearLayout(this);texts.setOrientation(LinearLayout.VERTICAL);texts.setPadding(dp(12),0,dp(8),0);
            entry.addView(texts,new LinearLayout.LayoutParams(0,-2,1));
            text(texts,item.title,15,INK,true);
            if(!item.detail.isEmpty()) text(texts,item.detail,12,item.tone==Attention.Tone.NEUTRAL?MUTED:tint,false);
            icon(entry,"chevron",MUTED,18);
            entry.setOnClickListener(v->{if(!busy)openAttention(item);});
            box.addView(entry,new LinearLayout.LayoutParams(-1,-2));
        }
    }
    private void openAttention(Attention.Item item) {
        if(item.deviceId!=null) {
            Device device=devicesReady() ? inventory().find(item.deviceId) : null;
            if(device!=null){ openDevice(device); return; }
            ControlStatus control=control();
            if(control!=null && control.has(item.deviceId)){ open("aircon",item.deviceId); return; }
        }
        if(!viewMode.equals("alerts")) tab("alerts");
    }
    private void categoryChips(List<Device> devices,double now) {
        HorizontalScrollView strip=new HorizontalScrollView(this);strip.setHorizontalScrollBarEnabled(false);
        LinearLayout row=new LinearLayout(this);strip.addView(row);
        for(String key:DeviceCategory.present(devices)) {
            LinearLayout chip=new LinearLayout(this);chip.setOrientation(LinearLayout.VERTICAL);chip.setPadding(dp(14),dp(10),dp(14),dp(12));
            chip.setBackground(ripple(SURFACE,16));chip.setClickable(true);chip.setFocusable(true);asButton(chip);chip.setMinimumWidth(dp(112));
            LinearLayout head=new LinearLayout(this);head.setGravity(Gravity.CENTER_VERTICAL);chip.addView(head);
            icon(head,DeviceCategory.icon(key),ACCENT,20);
            TextView label=text(head,DeviceCategory.label(key),14,INK,true);label.setPadding(dp(8),0,0,0);
            TextView summary=text(chip,DeviceText.category(key,devices,now),12,MUTED,false);summary.setSingleLine();
            chip.setOnClickListener(v->{if(!busy)open("category",key);});
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-2,-2);p.rightMargin=dp(8);row.addView(chip,p);
        }
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(8);page.addView(strip,p);
    }
    private void roomHeader(LinearLayout parent,String room,List<Device> devices) {
        LinearLayout head=new LinearLayout(this);head.setGravity(Gravity.CENTER_VERTICAL);head.setPadding(dp(4),dp(10),dp(4),dp(6));
        parent.addView(head,new LinearLayout.LayoutParams(-1,-2));
        TextView name=text(head,DeviceText.roomLabel(room),15,INK,true);name.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
        String climate=DeviceText.roomClimate(devices);
        if(climate!=null){
            TextView value=text(head,climate,13,MUTED,false);
            value.setCompoundDrawables(new FamilyIcon("thermometer",MUTED,dp(16)),null,null,null);value.setCompoundDrawablePadding(dp(4));
        }
    }
    /** Three tiles per row; the last row is padded so tiles keep their width. */
    private void grid(LinearLayout parent,List<Device> devices,double now) {
        LinearLayout row=null;
        for(int i=0;i<devices.size();i++) {
            if(i%3==0){ row=new LinearLayout(this);row.setBaselineAligned(false);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(8);parent.addView(row,p); }
            tile(row,devices.get(i),now,i%3);
        }
        if(row!=null) for(int column=devices.size()%3;column!=0 && column<3;column++) {
            LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,1,1);p.leftMargin=dp(4);p.rightMargin=column==2?0:dp(4);
            row.addView(new View(this),p);
        }
    }
    private void tile(LinearLayout row,Device device,double now,int column) {
        boolean stale=device.stale(now), open="open".equals(device.contact());
        String summary=DeviceText.tile(device,now,Attention.changedAt(device,events));
        LinearLayout tile=new LinearLayout(this);tile.setOrientation(LinearLayout.VERTICAL);tile.setPadding(dp(12),dp(10),dp(8),dp(12));
        tile.setBackground(ripple(SURFACE,16));tile.setClickable(true);tile.setFocusable(true);tile.setLongClickable(true);asButton(tile);
        tile.setMinimumHeight(dp(104));
        LinearLayout head=new LinearLayout(this);head.setGravity(Gravity.CENTER_VERTICAL);tile.addView(head,new LinearLayout.LayoutParams(-1,dp(36)));
        icon(head,DeviceCategory.typeIcon(device.type),open?DANGER:device.on()?ACCENT:INK,24);
        head.addView(new View(this),new LinearLayout.LayoutParams(0,1,1));
        if(device.batteryLow()){
            View battery=icon(head,"battery",WARNING,18);battery.setContentDescription("배터리 부족");
            battery.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        }
        if(device.aircon()) {
            boolean on=device.on();
            Button power=new Button(this);flatten(power);power.setBackground(circleIcon("power",on?ACCENT:RAISED,on?ON_ACCENT:MUTED,36,18));
            power.setPadding(0,0,0,0);power.setMinWidth(0);power.setMinimumWidth(0);power.setMinHeight(0);power.setMinimumHeight(0);
            power.setContentDescription(on?"에어컨 끄기":"에어컨 조작 열기");
            power.setOnClickListener(v->{if(!busy)airconPower(device);});power.setEnabled(!busy);buttons.add(power);
            LinearLayout.LayoutParams pp=new LinearLayout.LayoutParams(dp(36),dp(36));pp.leftMargin=dp(4);head.addView(power,pp);
        }
        TextView name=text(tile,device.shortName(),14,INK,true);name.setSingleLine();name.setEllipsize(TextUtils.TruncateAt.END);
        TextView value=text(tile,summary,12,open && !stale?DANGER:MUTED,false);value.setSingleLine();value.setEllipsize(TextUtils.TruncateAt.END);
        if(stale) tile.setAlpha(.55f);
        tile.setOnClickListener(v->{if(!busy)openDevice(device);});
        tile.setOnLongClickListener(v->{ if(!busy){ toggleFavorite(device.id); refreshView(); } return true; });
        // Wrap content, not match_parent: in a wrap_content row padded with spacer views, match_parent
        // children are left out of the row height and collapse to the 1 px spacer (seen on the A50).
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.leftMargin=column==0?0:dp(4);p.rightMargin=column==2?0:dp(4);
        row.addView(tile,p);
    }
    /** On (as far as the last command tells): confirm and send power_off. Off or unknown: open the control screen. */
    private void airconPower(Device device) {
        ControlStatus control=control();
        if(device.on() && control!=null && control.has(device.id) && airconSendable()) confirmAircon(device.id,device.name,"power_off");
        else openDevice(device);
    }

    // ---- 종류별 page ----

    private void categoryPage(String key) {
        viewMode="category";routeArg=key==null ? "" : key;generation++;working(false);
        String[] titles=titles();screen(titles[0],titles[1]);renderCategory();syncHome();
    }
    private void renderCategory() {
        if(!devicesReady()){ text(page,"기기를 확인하고 있어요…",14,MUTED,false); return; }
        double now=now();List<Device> members=DeviceCategory.members(inventory().devices,routeArg);
        if(members.isEmpty()){ text(page,"이 종류의 기기가 없어요",15,MUTED,false); return; }
        for(Map.Entry<String,List<Device>> room:DeviceText.rooms(members).entrySet()){
            roomHeader(page,room.getKey(),room.getValue());grid(page,room.getValue(),now);gap(page,4);
        }
    }

    // ---- Device detail (sensors and unknown devices) ----

    private void devicePage(String id) {
        Device device=devicesReady() ? inventory().find(id) : null;
        if(device!=null && device.aircon()){ airconPage(id); return; }
        viewMode="device";routeArg=id==null ? "" : id;generation++;working(false);
        String[] titles=titles();screen(titles[0],titles[1]);renderDevice();syncHome();
    }
    /** Columns of big values with a small label under each, up to three per card row. */
    private void metrics(List<Object[]> values) {
        for(int start=0;start<values.size();start+=3) {
            LinearLayout box=card();box.setOrientation(LinearLayout.HORIZONTAL);box.setPadding(dp(16),dp(14),dp(16),dp(14));
            for(int i=start;i<Math.min(values.size(),start+3);i++) {
                Object[] metric=values.get(i);
                LinearLayout column=new LinearLayout(this);column.setOrientation(LinearLayout.VERTICAL);
                box.addView(column,new LinearLayout.LayoutParams(0,-2,1));
                TextView big=text(column,(String)metric[0],30,(Integer)metric[2],true);big.setSingleLine();
                text(column,(String)metric[1],12,MUTED,false);
            }
        }
    }
    private void renderDevice() {
        if(!devicesReady()){ text(page,"기기를 확인하고 있어요…",14,MUTED,false); return; }
        Inventory inventory=inventory();Device device=inventory.find(routeArg);
        if(device==null){ text(page,"이 기기를 찾을 수 없어요",15,MUTED,false); return; }
        double now=now();boolean stale=device.stale(now);
        String status=stale ? DeviceText.NO_RESPONSE+" · "+DeviceText.duration(now-device.reportedAt)
            : device.reportedAt!=null ? DeviceText.ago(now-device.reportedAt)+" 보고" : "";
        if(inventory.hubProblem(now)) status="Pi 연결 끊김"+(status.isEmpty() ? "" : " · "+status);
        if(!status.isEmpty()){ TextView line=text(page,status,13,stale?WARNING:MUTED,false);line.setPadding(dp(4),0,0,dp(10)); }
        List<Object[]> values=new ArrayList<>();
        String contact=device.contact();
        if(contact!=null) {
            Double changed=Attention.changedAt(device,events);if(changed==null)changed=device.reportedAt;
            values.add(new Object[]{contact.equals("open")?"열림":"닫힘","문"+(changed==null?"":" · "+DeviceText.ago(now-changed)),contact.equals("open")?DANGER:INK});
        }
        Double temperature=device.number("temperature_c"), humidity=device.number("humidity_percent");
        if(temperature!=null) values.add(new Object[]{DeviceText.number(temperature)+"°","온도",INK});
        if(humidity!=null) values.add(new Object[]{DeviceText.number(humidity)+"%","습도",INK});
        if(device.state.containsKey("power") || device.capabilities.contains("power")) {
            Boolean power=device.power();
            values.add(new Object[]{power==null?"—":power?"켜짐":"꺼짐","전원",Boolean.TRUE.equals(power)?ACCENT:INK});
        }
        Double brightness=device.number("brightness_percent"), colour=device.number("color_temp_k"), watts=device.number("power_w");
        if(brightness!=null) values.add(new Object[]{DeviceText.number(brightness)+"%","밝기",INK});
        if(colour!=null) values.add(new Object[]{DeviceText.number(colour)+"K","색온도",INK});
        if(watts!=null) values.add(new Object[]{DeviceText.number(watts)+"W","소비 전력",INK});
        Boolean motion=device.flag("motion"), leak=device.flag("leak"), smoke=device.flag("smoke");
        if(motion!=null) values.add(new Object[]{motion?"감지":"없음","움직임",motion?ACCENT:INK});
        if(leak!=null) values.add(new Object[]{leak?"감지":"정상","누수",leak?DANGER:INK});
        if(smoke!=null) values.add(new Object[]{smoke?"감지":"정상","연기",smoke?DANGER:INK});
        metrics(values);
        if(device.hasBattery()) {
            Integer percent=device.batteryPercent();boolean low=device.batteryLow();
            LinearLayout battery=card();battery.setOrientation(LinearLayout.HORIZONTAL);battery.setGravity(Gravity.CENTER_VERTICAL);
            battery.setPadding(dp(16),dp(12),dp(16),dp(12));
            icon(battery,"battery",low?WARNING:MUTED,22);
            TextView label=text(battery,"배터리",14,INK,false);label.setPadding(dp(12),0,0,0);label.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
            text(battery,percent!=null ? percent+"%"+(low?" · 부족":"") : low ? "부족" : "—",16,low?WARNING:INK,true);
        }
        // Blocks this app does not know yet: plain name/value rows.
        List<String[]> rows=new ArrayList<>();
        for(Map.Entry<String,Object> entry:device.state.entrySet())
            if(!KNOWN_STATE.contains(entry.getKey())) rows.add(new String[]{entry.getKey(),DeviceText.value(entry.getValue())});
        for(String capability:device.capabilities)
            if(!KNOWN_CAPABILITIES.contains(capability) && !device.state.containsKey(capability)) rows.add(new String[]{capability,"지원"});
        if(!rows.isEmpty()) {
            LinearLayout other=card();other.setPadding(dp(16),dp(6),dp(16),dp(6));
            for(int i=0;i<rows.size();i++) {
                if(i>0) divider(other);
                LinearLayout line=new LinearLayout(this);line.setPadding(0,dp(8),0,dp(8));other.addView(line,new LinearLayout.LayoutParams(-1,-2));
                TextView key=text(line,rows.get(i)[0],14,MUTED,false);key.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
                text(line,rows.get(i)[1],14,INK,true);
            }
        }
        section("최근 기록");
        LinearLayout list=card();list.setPadding(dp(14),dp(4),dp(14),dp(4));
        if(!eventsLoaded){ text(list,eventsError!=null?eventsError:"기록을 확인하고 있어요…",14,MUTED,false); return; }
        ZoneId zone=ZoneId.systemDefault();int shown=0;
        for(AppEvent event:events) {
            if(shown>=10 || !Timeline.belongsTo(event,device)) continue;
            if(shown>0) divider(list);
            LinearLayout entry=new LinearLayout(this);entry.setOrientation(LinearLayout.VERTICAL);entry.setPadding(0,dp(8),0,dp(8));list.addView(entry);
            text(entry,Timeline.title(event,device.name),15,INK,false);
            text(entry,Timeline.dayLabel(event.receivedAt,now,zone)+" "+Timeline.clock(event.receivedAt,zone),12,MUTED,false);
            shown++;
        }
        if(shown==0) text(list,"아직 기록이 없어요",14,MUTED,false).setPadding(0,dp(10),0,dp(10));
    }

    // ---- Aircon control ----

    private void airconPage(String device) {
        selectedAircon=device;viewMode="aircon";routeArg=device==null ? "" : device;generation++;working(false);
        String[] titles=titles();screen(titles[0],titles[1]);
        renderAirconControls();syncHome();
    }
    private void stepState(Button button,boolean enabled) { button.setEnabled(enabled);button.setAlpha(enabled?1f:.35f); }
    private void airconSendState(Button button,boolean enabled) {
        button.setEnabled(enabled && !busy);
        button.setTag(enabled?"aircon-enabled":"aircon-disabled");
        button.setAlpha(enabled?1f:.45f);
    }
    /** Fits one phone screen: status line, dial with −/+, modes, fan, extras, and the pinned power/send footer. */
    private void renderAirconControls() {
        // The pinned footer lives outside the page, so every rebuild clears it and forgets its buttons.
        footer.removeAllViews();footer.setPadding(0,0,0,0);buttons.removeIf(b->!insideShell(b));
        if(airconError!=null){LinearLayout error=card();text(error,airconError,14,DANGER,false);button(error,"연결 다시 확인",true,this::loadAircon);return;}
        if(!airconLoaded || aircon==null){text(page,"에어컨 연결을 확인하고 있어요…",14,MUTED,false);return;}
        final ControlStatus control=control();
        if(selectedAircon==null || !control.has(selectedAircon)){
            text(page,"이 에어컨은 지금 조작할 수 없어요.",15,MUTED,false);button(page,"뒤로",false,this::back);return;
        }
        final String id=selectedAircon, name=airconName(id);
        final AirconUi.Draft draft=airconDrafts.computeIfAbsent(id,key->new AirconUi.Draft());
        ControlStatus.Command latest=control.latestFor(id);
        String state=control.latest==null ? "" : control.latest.state;
        boolean allowed=control.canControl, online=control.online;
        boolean enabled=AirconUi.canSend(allowed,online,state);
        final Runnable[] sync=new Runnable[1];

        // One status line: Pi connection, then this aircon's last command ("1분 전 · 냉방 24° · 전달됨").
        LinearLayout status=new LinearLayout(this);status.setGravity(Gravity.CENTER_VERTICAL);page.addView(status,new LinearLayout.LayoutParams(-1,-2));
        statusChip(status,online);
        StringBuilder line=new StringBuilder();
        if(!allowed) line.append("조회 전용");
        if(latest!=null){
            if(line.length()>0) line.append(" · ");
            line.append(DeviceText.ago(now()-latest.time())).append(" · ").append(AirconUi.shortLabel(latest.action));
            String label=AirconUi.stateLabel(latest.state);if(!label.isEmpty()) line.append(" · ").append(label);
        }
        boolean problem=latest!=null && AirconUi.problem(latest.state);
        TextView summary=text(status,line.toString(),13,problem?DANGER:MUTED,false);summary.setPadding(dp(10),0,0,0);
        summary.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));summary.setMaxLines(2);
        if(problem){ TextView why=text(page,AirconUi.description(latest.state,latest.action),12,DANGER,false);why.setPadding(dp(2),dp(4),0,0); }

        // Temperature dial between −/+ steps. Values only change the unsent draft.
        LinearLayout dialRow=new LinearLayout(this);dialRow.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams dialRowParams=new LinearLayout.LayoutParams(-1,-2);dialRowParams.topMargin=dp(4);page.addView(dialRow,dialRowParams);
        Button down=roundButton(dialRow,"minus",RAISED,INK,44,"1도 내리기",()->{draft.temperature=Math.max(TemperatureDial.MIN,draft.temperature-1);sync[0].run();});
        TemperatureDial dial=new TemperatureDial(this,RAISED,ACCENT,INK,MUTED);
        dial.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        LinearLayout.LayoutParams dialParams=new LinearLayout.LayoutParams(0,dp(228),1);dialParams.leftMargin=dp(4);dialParams.rightMargin=dp(4);
        dialRow.addView(dial,dialParams);
        dial.setListener(t->{draft.temperature=t;sync[0].run();});
        Button up=roundButton(dialRow,"add",RAISED,INK,44,"1도 올리기",()->{draft.temperature=Math.min(TemperatureDial.MAX,draft.temperature+1);sync[0].run();});

        // Operating modes as round icon buttons.
        LinearLayout modes=new LinearLayout(this);LinearLayout.LayoutParams modeParams=new LinearLayout.LayoutParams(-1,-2);modeParams.topMargin=dp(4);
        page.addView(modes,modeParams);
        String[] modeIcons={"snowflake","auto","droplet","wind"};
        LinearLayout[] modeItems=new LinearLayout[AirconUi.MODES.length];View[] modeCircles=new View[AirconUi.MODES.length];TextView[] modeLabels=new TextView[AirconUi.MODES.length];
        for(int i=0;i<AirconUi.MODES.length;i++){
            final int index=i;
            LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setGravity(Gravity.CENTER_HORIZONTAL);item.setPadding(0,dp(2),0,0);
            item.setClickable(true);item.setFocusable(true);item.setContentDescription(AirconUi.MODES[i]+" 모드");asButton(item);
            View circle=new View(this);circle.setDuplicateParentStateEnabled(true);circle.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            item.addView(circle,new LinearLayout.LayoutParams(dp(48),dp(48)));
            TextView label=text(item,AirconUi.MODES[i],12,MUTED,false);label.setGravity(Gravity.CENTER);
            item.setOnClickListener(v->{if(busy)return;draft.mode=index;sync[0].run();});
            modes.addView(item,new LinearLayout.LayoutParams(0,-2,1));
            modeItems[i]=item;modeCircles[i]=circle;modeLabels[i]=label;
        }

        // Cooling fan: 자동 pill plus three bars of growing height for 약·중·강.
        LinearLayout fan=new LinearLayout(this);fan.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams fanParams=new LinearLayout.LayoutParams(-1,-2);fanParams.topMargin=dp(6);page.addView(fan,fanParams);
        TextView fanLabel=text(fan,"바람",13,MUTED,true);fanLabel.setPadding(dp(4),0,dp(10),0);
        Button auto=chip(fan,"자동",()->{draft.fan=0;sync[0].run();});auto.setContentDescription("바람 자동");
        auto.setLayoutParams(new LinearLayout.LayoutParams(-2,dp(48)));
        View[] bars=new View[FanLevels.BARS];LinearLayout[] barItems=new LinearLayout[FanLevels.BARS];
        for(int bar=1;bar<=FanLevels.BARS;bar++){
            final int level=bar;
            LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setGravity(Gravity.CENTER_HORIZONTAL|Gravity.BOTTOM);
            item.setClickable(true);item.setFocusable(true);item.setContentDescription("바람 "+AirconUi.FANS[level]);asButton(item);
            item.setBackground(ripple(Color.TRANSPARENT,12));item.setPadding(0,dp(4),0,0);
            View fill=new View(this);fill.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            item.addView(fill,new LinearLayout.LayoutParams(dp(26),dp(10*FanLevels.heightQuarters(level))));
            TextView label=text(item,FanLevels.SHORT[level],12,MUTED,false);label.setGravity(Gravity.CENTER);
            item.setOnClickListener(v->{if(busy)return;draft.fan=level;sync[0].run();});
            LinearLayout.LayoutParams itemParams=new LinearLayout.LayoutParams(0,dp(64),1);itemParams.leftMargin=dp(4);fan.addView(item,itemParams);
            bars[level-1]=fill;barItems[level-1]=item;
        }

        // One-shot extras: each opens the same confirmation dialog. They wrap instead of scrolling
        // sideways: on a portrait A50 the last chip was cut off and easy to miss.
        FlowRow extras=new FlowRow(this,dp(8),dp(8));
        LinearLayout.LayoutParams extrasParams=new LinearLayout.LayoutParams(-1,-2);extrasParams.topMargin=dp(6);page.addView(extras,extrasParams);
        String[][] extraActions={{"풍향 고정","airflow_fix"},{"스윙 바꾸기","swing_toggle"},{"절전","economy"},{"터보","turbo"},{"표시등 바꾸기","led_toggle"}};
        for(String[] extra:extraActions){
            Button chip=chip(extras,extra[0],()->confirmAircon(id,name,extra[1]));airconSendState(chip,enabled);
        }

        // Pinned footer: power off and send stay reachable without scrolling.
        LinearLayout actions=new LinearLayout(this);actions.setGravity(Gravity.CENTER_VERTICAL);
        pinnedFooter().addView(actions,new LinearLayout.LayoutParams(-1,-2));
        Button power=roundButton(actions,"power",DANGER_SURFACE,DANGER,52,"에어컨 끄기",()->confirmAircon(id,name,"power_off"));
        buttons.add(power);airconSendState(power,enabled);
        Button send=button(actions,"설정 보내기",true,()->confirmAircon(id,name,draft.action()));
        LinearLayout.LayoutParams sendParams=new LinearLayout.LayoutParams(0,dp(52),1);sendParams.leftMargin=dp(12);send.setLayoutParams(sendParams);
        airconSendState(send,enabled);

        sync[0]=()->{
            boolean cool=draft.mode==0;
            dial.bind(cool,draft.temperature,AirconUi.MODES[draft.mode],FanLevels.dialCaption(draft.mode,draft.fan));
            stepState(down,cool && draft.temperature>TemperatureDial.MIN);
            stepState(up,cool && draft.temperature<TemperatureDial.MAX);
            for(int i=0;i<modeItems.length;i++){
                boolean active=draft.mode==i;
                modeCircles[i].setBackground(circleIcon(modeIcons[i],active?ACCENT:RAISED,active?ON_ACCENT:INK,48,22));
                modeLabels[i].setTextColor(active?INK:MUTED);modeLabels[i].setTypeface(Typeface.DEFAULT,active?Typeface.BOLD:Typeface.NORMAL);
                modeItems[i].setSelected(active);
            }
            fan.setVisibility(cool?View.VISIBLE:View.GONE);
            chipStyle(auto,draft.fan==0);
            for(int bar=1;bar<=FanLevels.BARS;bar++){
                bars[bar-1].setBackground(shape(FanLevels.filled(bar,draft.fan)?ACCENT:LINE,6));
                barItems[bar-1].setSelected(draft.fan==bar);
            }
        };
        sync[0].run();
    }
    private boolean airconSendable() {
        if(aircon==null)return false;
        JSONObject latest=aircon.optJSONObject("latest_command");
        return AirconUi.canSend(aircon.optBoolean("can_control"),aircon.optBoolean("online"),latest==null?"":latest.optString("state"));
    }
    private void confirmAircon(String device,String name,String action) {
        // A double tap must not stack two dialogs that each send their own command.
        if(commandDialog!=null && commandDialog.isShowing())return;
        final String home=currentHome;
        commandDialog=new AlertDialog.Builder(this).setTitle("명령을 보낼까요?")
            .setMessage(name+"\n"+AirconUi.confirmation(action))
            .setNegativeButton("취소",null).setPositiveButton("보내기",(dialog,which)->{
                if(home==null || !home.equals(currentHome) || !inHome(viewMode))return;
                if(busy || !airconSendable()){message("지금은 보낼 수 없어요. 연결 상태와 최근 요청을 확인해 주세요.");return;}
                final String id=java.util.UUID.randomUUID().toString();
                request("POST","/v1/homes/"+home+"/control/commands",json("request_id",id,"device_id",device,"action",action),reply->{
                    try{aircon.put("latest_command",reply);}catch(JSONException ignored){}
                    refreshAirconView();pollAircon(home,id,generation,0);
                },detail->{
                    message(detail+" 명령은 자동으로 다시 보내지 않아요.");
                    loadAircon();
                });
            }).show();
    }
    private void pollAircon(String home,String id,int epoch,int attempt) {
        if(attempt==0 && !poll.start(id,epoch))return;
        if(!poll.active(id,epoch))return;
        if(stopped){poll.cancel();resumeAircon=true;return;}
        if(attempt>=CommandPoll.MAX_ATTEMPTS){poll.finish(id);airconError="연결이 끊겨 결과를 확인하지 못했어요. 다시 누르기 전에 에어컨을 확인해 주세요.";refreshAirconView();return;}
        ui.postDelayed(()->{
            if(!poll.active(id,epoch))return;
            if(epoch!=generation || isDestroyed() || !home.equals(currentHome) || !inHome(viewMode)){poll.finish(id);return;}
            request("GET","/v1/homes/"+home+"/control/commands/"+id,null,reply->{
                if(!poll.active(id,epoch))return;
                JSONObject latest=aircon==null?null:aircon.optJSONObject("latest_command");
                if(aircon==null || !CommandPoll.current(latest==null?null:latest.optString("id"),id)){poll.finish(id);return;}
                String state=reply.optString("state");boolean changed=latest==null || !state.equals(latest.optString("state"));
                try{aircon.put("latest_command",reply);}catch(JSONException ignored){}
                // Rebuild only on a state change so a dial drag or a scroll is not interrupted every tick.
                if(changed)refreshAirconView();
                if(AirconUi.pending(state))pollAircon(home,id,epoch,attempt+1);else poll.finish(id);
            },(detail,failure)->{
                if(!poll.active(id,epoch))return;
                ApiClient.Failure f=failure instanceof ApiClient.Failure?(ApiClient.Failure)failure:null;
                if(f!=null && (!CommandPoll.retryable(f.status) || f.code.startsWith("server_identity"))){poll.finish(id);airconError=detail;refreshAirconView();return;}
                pollAircon(home,id,epoch,attempt+1);
            },true);
        },2000);
    }

    // ---- 알림 tab ----

    private void alertsPage() {
        if(currentHome==null){start();return;}
        viewMode="alerts";routeArg="";generation++;working(false);
        screen("알림","");renderAlerts();syncHome();
    }
    private void filterChip(LinearLayout parent,String label,String key) {
        Button chip=chip(parent,label,()->{eventFilter=key;expanded.clear();replacePage(this::renderAlerts);});
        chipStyle(chip,eventFilter.equals(key));chip.setSingleLine();
        ((LinearLayout.LayoutParams)chip.getLayoutParams()).rightMargin=dp(6);
    }
    private void renderAlerts() {
        if(currentHouse==null && homeError!=null){ homeLoading(); return; }
        double now=now();boolean ready=devicesReady();
        Inventory inventory=ready ? inventory() : null;
        List<Attention.Item> items=ready ? Attention.compute(inventory,events,control(),now) : new ArrayList<>();
        Map<String,String> names=inventory==null ? new HashMap<>() : inventory.names();
        Map<String,String> levels=PushManager.levels(PushManager.prefs(this));
        Set<String> present=new HashSet<>();
        for(AppEvent event:events) present.add(event.alertCategory());
        for(Attention.Item item:items) present.add(item.category);
        if(!eventFilter.equals("all") && !present.contains(eventFilter)) eventFilter="all";
        HorizontalScrollView strip=new HorizontalScrollView(this);strip.setHorizontalScrollBarEnabled(false);
        LinearLayout chips=new LinearLayout(this);strip.addView(chips);
        filterChip(chips,"전체","all");
        for(String category:AlertLevels.FILTERS) if(present.contains(category)) filterChip(chips,AlertLevels.label(category),category);
        LinearLayout.LayoutParams stripParams=new LinearLayout.LayoutParams(-1,-2);stripParams.bottomMargin=dp(6);page.addView(strip,stripParams);
        List<Attention.Item> open=Attention.filter(items,eventFilter);
        if(!open.isEmpty()){ section("해결 안 됨"); attentionList(open); }
        if(!eventsLoaded){
            if(eventsError!=null){ LinearLayout failed=card();text(failed,eventsError,14,MUTED,false);button(failed,"다시 확인",false,this::refreshHome); }
            else text(page,"기록을 확인하고 있어요…",14,MUTED,false);
            return;
        }
        List<AppEvent> visible=new ArrayList<>();int hidden=0;
        for(AppEvent event:events) {
            String category=event.alertCategory();
            if(eventFilter.equals("all")) { if(AlertLevels.showsInAll(category,levels.get(category))) visible.add(event); else hidden++; }
            else if(category.equals(eventFilter)) visible.add(event);
        }
        if(visible.isEmpty()) {
            LinearLayout empty=card();
            text(empty,eventFilter.equals("all")?"아직 도착한 기록이 없어요":"이 종류의 기록은 아직 없어요",16,INK,true);
        }
        ZoneId zone=ZoneId.systemDefault();
        for(Timeline.Day day:Timeline.build(visible,names,zone,now)) {
            section(day.label);
            LinearLayout list=card();list.setPadding(dp(14),dp(2),dp(14),dp(2));
            for(int i=0;i<day.rows.size();i++){ if(i>0) divider(list); timelineRow(list,day.rows.get(i),names,inventory,zone); }
        }
        if(hidden>0){ TextView note=text(page,"끔으로 둔 종류의 기록 "+hidden+"개는 숨겼어요",12,MUTED,false);note.setPadding(dp(4),0,0,0); }
    }
    private void timelineRow(LinearLayout parent,Timeline.Row row,Map<String,String> names,Inventory inventory,ZoneId zone) {
        AppEvent first=row.newest();String category=first.alertCategory();
        int tint=category.equals(AlertLevels.SAFETY) || category.equals(AlertLevels.AUTOMATION) ? WARNING : category.equals(AlertLevels.OTHER) ? MUTED : ACCENT;
        LinearLayout entry=new LinearLayout(this);entry.setOrientation(LinearLayout.VERTICAL);entry.setPadding(0,dp(10),0,dp(10));
        parent.addView(entry,new LinearLayout.LayoutParams(-1,-2));
        TextView title=text(entry,Timeline.title(row,names),15,INK,true);
        title.setCompoundDrawables(new FamilyIcon(Timeline.icon(category),tint,dp(21)),null,row.count()>1?new FamilyIcon("expand",MUTED,dp(18)):null,null);
        title.setCompoundDrawablePadding(dp(10));
        TextView time=text(entry,Timeline.time(row,zone),12,MUTED,false);time.setPadding(dp(31),dp(2),0,dp(2));
        if(row.count()>1) {
            final String key=row.key();
            entry.setClickable(true);entry.setFocusable(true);asButton(entry);entry.setBackground(ripple(Color.TRANSPARENT,10));
            entry.setOnClickListener(v->{if(busy)return;if(!expanded.remove(key))expanded.add(key);replacePage(this::renderAlerts);});
            if(expanded.contains(key)) for(AppEvent event:row.events) {
                TextView item=text(entry,Timeline.clock(event.receivedAt,zone)+"  "+Timeline.title(event,Timeline.name(event,names)),13,MUTED,false);
                item.setPadding(dp(31),dp(2),0,dp(2));
            }
        } else {
            final Device device=inventory==null ? null : inventory.find(first.deviceId);
            if(device!=null) {
                entry.setClickable(true);entry.setFocusable(true);asButton(entry);entry.setBackground(ripple(Color.TRANSPARENT,10));
                entry.setOnClickListener(v->{if(!busy)openDevice(device);});
            }
        }
    }

    // ---- 설정 tab ----

    private void settingsPage() {
        if(currentHome==null){start();return;}
        viewMode="settings";routeArg="";generation++;working(false);
        screen("설정","");renderSettings();
        if(currentHouse==null) syncHome();
    }
    private static String clock(int minutes) { return String.format(java.util.Locale.ROOT,"%02d:%02d",minutes/60,minutes%60); }
    private void renderSettings() {
        SharedPreferences p=PushManager.prefs(this);
        section("이 휴대폰 알림");
        LinearLayout phone=card();
        if(BuildConfig.FLAVOR.equals("production")){
            GradientDrawable background=shape(SURFACE,18);background.setStroke(dp(1),LINE);phone.setBackground(background);
            pushStatus=text(phone,"",18,INK,true);pushStatus.setCompoundDrawables(new FamilyIcon("bell",ACCENT,dp(22)),null,null,null);pushStatus.setCompoundDrawablePadding(dp(10));
            pushDetail=text(phone,"",13,MUTED,false);
            pushToggle=preferenceSwitch(phone,"이 휴대폰에서 받기",p.getBoolean("enabled",false));
            pushToggle.setOnCheckedChangeListener((v,checked)->{if(updatingPushControls)return;if(checked)enableNotifications();else {PushManager.disable(this);refreshPushStatus();}});
            pushReceipt=text(phone,"최근 알림 수신 완료",12,ONLINE,true);
            row(phone,"refresh","알림 연결 확인","",()->{PushManager.sync(this);refreshPushStatus();message("연결 상태를 확인하고 있어요.");});
            if(owner()) row(phone,"bell","시험 알림 보내기","",()->testNotification(currentHome));
            row(phone,"settings","휴대폰 알림 설정 열기","",()->startActivity(new android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName())));
        } else text(phone,"동작 시험 앱은 알림을 받지 않아요.",13,MUTED,false);

        Map<String,String> levels=PushManager.levels(p);
        section("알림 종류별 중요도");
        LinearLayout table=card();table.setPadding(dp(8),dp(4),dp(8),dp(4));
        for(int i=0;i<AlertLevels.CATEGORIES.length;i++) {
            final String category=AlertLevels.CATEGORIES[i];
            if(i>0) divider(table);
            valueRow(table,AlertLevels.label(category),AlertLevels.caption(category),AlertLevels.levelLabel(levels.get(category)),()->levelDialog(category));
        }
        if(AlertLevels.reportIntervalVisible(levels.get(AlertLevels.REPORT))) {
            section("정기 보고 간격");
            LinearLayout box=card();box.setPadding(dp(12),dp(6),dp(12),dp(6));
            LinearLayout options=new LinearLayout(this);box.addView(options,new LinearLayout.LayoutParams(-1,-2));
            int selected=PushManager.reportInterval(p);
            for(int minute:AlertLevels.INTERVALS) {
                Button option=chip(options,minute+"분",()->{PushManager.reportInterval(this,minute);replacePage(this::renderSettings);});
                chipStyle(option,minute==selected);option.setPadding(0,0,0,0);option.setContentDescription("정기 보고 간격 "+minute+"분");
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(48),1);lp.rightMargin=dp(4);option.setLayoutParams(lp);
            }
        }
        section("방해 금지 시간");
        LinearLayout quiet=card();quiet.setPadding(dp(12),dp(4),dp(8),dp(8));
        final boolean quietOn=PushManager.quietEnabled(p);final int start=PushManager.quietStart(p), end=PushManager.quietEnd(p);
        Switch toggle=preferenceSwitch(quiet,"정한 시간에는 조용히 받기",quietOn);
        toggle.setOnCheckedChangeListener((v,checked)->{
            PushManager.quietHours(this,checked,start,end);
            page.post(()->{if(viewMode.equals("settings"))replacePage(this::renderSettings);});
        });
        if(quietOn) {
            divider(quiet);valueRow(quiet,"시작","",clock(start),()->pickQuietTime(true));
            divider(quiet);valueRow(quiet,"끝","",clock(end),()->pickQuietTime(false));
        }
        TextView note=text(quiet,"긴급 알림은 울려요",12,MUTED,false);note.setPadding(0,dp(4),0,0);

        if(currentHouse!=null) {
            section("집 관리");LinearLayout house=card();house.setPadding(dp(8),dp(8),dp(8),dp(8));
            LinearLayout houseHead=new LinearLayout(this);houseHead.setGravity(Gravity.CENTER_VERTICAL);houseHead.setPadding(dp(8),dp(4),0,dp(8));house.addView(houseHead);
            badge(houseHead,"home",RAISED,ACCENT,40,20);
            LinearLayout houseTexts=new LinearLayout(this);houseTexts.setOrientation(LinearLayout.VERTICAL);houseTexts.setPadding(dp(12),0,0,0);houseHead.addView(houseTexts,new LinearLayout.LayoutParams(0,-2,1));
            text(houseTexts,currentHouse.optString("name"),17,INK,true);text(houseTexts,role(currentHouse.optString("role")),12,MUTED,false);
            divider(house);row(house,"home","집 바꾸기","",this::homeSwitcher);
            if(owner()) {
                divider(house);row(house,"family","가족 초대 만들기","",()->invite(currentHome));
                divider(house);row(house,"family","가족 관리","",()->open("members",""));
                divider(house);row(house,"hub","Pi 허브 연결","",this::claimHub);
                divider(house);row(house,"hub","Pi 허브 연결 해제","",this::revokeHub);
            } else { TextView only=text(house,"가족 초대와 기기 등록은 소유자가 관리해요.",13,MUTED,false);only.setPadding(dp(8),dp(6),dp(8),0); }
        }
        section("연결 및 계정");LinearLayout account=card();account.setPadding(dp(8),dp(6),dp(8),dp(10));
        row(account,"network","연결 설정","",this::connectionSettings);divider(account);row(account,"logout","로그아웃","",this::logout);
        divider(account);fingerprintNote(account);
        if(owner()) {
            LinearLayout danger=card();danger.setBackground(shape(DANGER_SURFACE,18));danger.setPadding(dp(8),dp(6),dp(8),dp(12));
            Button remove=row(danger,"trash","이 집 삭제","",()->deleteHome(currentHome,currentHouse.optString("name")));remove.setTextColor(DANGER);
            remove.setCompoundDrawables(new FamilyIcon("trash",DANGER,dp(22)),null,new FamilyIcon("chevron",DANGER,dp(18)),null);
            TextView dangerNote=text(danger,"모든 가족의 접근과 연결 기기의 알림이 중지돼요.",12,DANGER,false);dangerNote.setPadding(dp(8),0,dp(8),0);dangerNote.setAlpha(.85f);
        }
        TextView version=text(page,"가족 스마트홈 · "+BuildConfig.VERSION_NAME,12,MUTED,false);version.setGravity(Gravity.CENTER);version.setPadding(0,dp(8),0,0);
        refreshPushStatus();
    }
    /** One choice per level with its meaning; 안전 only offers 긴급 and 알림. Saved at once for this phone only. */
    private void levelDialog(String category) {
        final String[] choices=AlertLevels.allowed(category);
        final String current=PushManager.level(PushManager.prefs(this),category);
        CharSequence[] items=new CharSequence[choices.length];int checked=-1;
        for(int i=0;i<choices.length;i++){
            items[i]=twoLines(AlertLevels.levelLabel(choices[i]),AlertLevels.levelMeaning(choices[i]));
            if(choices[i].equals(current)) checked=i;
        }
        new AlertDialog.Builder(this).setTitle(AlertLevels.label(category)+" · "+AlertLevels.caption(category)).setSingleChoiceItems(items,checked,(dialog,which)->{
            dialog.dismiss();
            if(choices[which].equals(current)) return;
            PushManager.level(this,category,choices[which]);
            if(viewMode.equals("settings")) replacePage(this::renderSettings);
        }).setNegativeButton("취소",null).show();
    }
    private void pickQuietTime(boolean startTime) {
        SharedPreferences p=PushManager.prefs(this);
        final int start=PushManager.quietStart(p), end=PushManager.quietEnd(p), value=startTime?start:end;
        new TimePickerDialog(this,(view,hour,minute)->{
            int chosen=hour*60+minute;
            PushManager.quietHours(this,true,startTime?chosen:start,startTime?end:chosen);
            if(viewMode.equals("settings")) replacePage(this::renderSettings);
        },value/60,value%60,true).show();
    }
    private void claimHub() {
        if(currentHome==null) return;
        final String home=currentHome;
        singleInput("Pi 허브 연결","10분 동안 유효한 등록 코드",128,code->request("POST","/v1/homes/"+home+"/hubs/claim",json("claim_code",code),reply->{
            message("Pi 허브를 연결했어요.");refreshHome();
        }));
    }
    private void revokeHub() {
        if(currentHome==null) return;
        final String home=currentHome;
        request("GET","/v1/homes/"+home+"/hubs",null,reply->{
            JSONArray hubs=reply.optJSONArray("hubs");List<String> active=new ArrayList<>();
            if(hubs!=null) for(int i=0;i<hubs.length();i++){ JSONObject hub=hubs.optJSONObject(i); if(hub!=null && hub.optInt("active")==1) active.add(hub.optString("id")); }
            if(active.isEmpty()){ message("연결된 Pi 허브가 없어요."); return; }
            CharSequence[] labels=new CharSequence[active.size()];
            for(int i=0;i<labels.length;i++) labels[i]="Pi 허브 · "+active.get(i).substring(0,Math.min(8,active.get(i).length()));
            new AlertDialog.Builder(this).setTitle("연결을 해제할 Pi 허브").setItems(labels,(chooser,which)->
                new AlertDialog.Builder(this).setTitle("Pi 허브 연결을 해제할까요?")
                    .setMessage("이 집의 기기 목록과 에어컨 조작, 기록 전달이 멈춰요. 다시 쓰려면 새 등록 코드로 연결해야 해요.")
                    .setNegativeButton("취소",null).setPositiveButton("연결 해제",(confirm,w)->
                        request("POST","/v1/homes/"+home+"/hubs/"+active.get(which)+"/revoke",new JSONObject(),done->{
                            message("Pi 허브 연결을 해제했어요.");refreshHome();
                        })).show()).setNegativeButton("닫기",null).show();
        });
    }
    private void deleteHome(String id,String name) {
        EditText input=new EditText(this); input.setSingleLine(); input.setHint(name);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("이 집을 삭제할까요?")
            .setMessage("모든 가족의 집 목록에서 사라지고 연결 기기의 접근과 알림이 중지돼요.\n다시 사용하려면 새 집을 만들고 기기를 등록해야 해요.\n\n확인을 위해 집 이름을 입력해 주세요: "+name)
            .setView(input).setNegativeButton("취소",null).setPositiveButton("집 삭제",null).create();
        dialog.setOnShowListener(unused->dialog.getButton(-1).setOnClickListener(view->{
            if(!name.equals(input.getText().toString().trim())) { input.setError("집 이름을 정확히 입력해 주세요."); return; }
            dialog.dismiss(); request("DELETE","/v1/homes/"+id,json("confirmation_name",name),reply->{
                message("집을 삭제했어요.");forgetHome(id);currentHome=null;clearHomeData();start();
            });
        }));dialog.show();
    }
    private void notificationHelp(String title,String detail) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(detail)
            .setPositiveButton("알림 설정",(dialog,which)->{ if(currentHome!=null) tab("settings"); }).setNegativeButton("닫기",null).show();
    }
    private boolean notificationsAllowed() {
        android.app.NotificationManager manager=getSystemService(android.app.NotificationManager.class);
        android.app.NotificationChannel channel=manager.getNotificationChannel(PushManager.CHANNEL);
        return manager.areNotificationsEnabled() && (channel==null || channel.getImportance()!=android.app.NotificationManager.IMPORTANCE_NONE);
    }
    private void testNotification(String id) {
        String account=session.userId(); if(account==null){ logout(); return; }
        android.content.SharedPreferences p=PushManager.prefs(this);
        if(!p.getBoolean("enabled",false) || !endpoint.equals(p.getString("origin",""))
                || !account.equals(p.getString("account",""))) {
            notificationHelp("이 휴대폰 알림을 켜주세요","설정의 ‘이 휴대폰 알림’에서 ‘이 휴대폰에서 받기’를 켜고 연결을 확인해 주세요.");
            return;
        }
        if(!notificationsAllowed()) {
            notificationHelp("휴대폰에서 알림을 허용해 주세요","휴대폰 설정에서 ‘가족 스마트홈’ 앱과 ‘우리 집 알림’의 알림을 허용해 주세요.");
            return;
        }
        if(p.getBoolean("registration_error",false)) {
            notificationHelp("알림 연결을 확인해 주세요",p.getString("registration_error_message","알림 연결 상태를 확인한 뒤 다시 시도해 주세요."));
            return;
        }
        if(p.getString("binding","").isEmpty() || p.getBoolean("preferences_pending",false)) {
            PushManager.sync(this);
            notificationHelp("알림 연결 준비 중이에요","잠시 후 ‘알림 연결 확인’을 눌러 주세요. ‘알림 연결됨’이 되면 시험 알림을 보낼 수 있어요.");
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
        String detail=!enabled?"켜면 아래에서 고른 중요도대로 받아요.":!notificationsAllowed()?"휴대폰 설정에서 앱 알림을 허용해 주세요."
            :p.getBoolean("registration_error",false)?p.getString("registration_error_message","인터넷 연결을 확인한 뒤 다시 시도해 주세요.")
            :p.getBoolean("preferences_pending",false)||p.getString("binding","").isEmpty()?"휴대폰을 연결하고 고른 중요도를 적용하고 있어요.":"이 휴대폰에만 적용돼요.";
        if(pushDetail!=null)pushDetail.setText(detail);
        if(pushReceipt!=null){pushReceipt.setVisibility(p.getLong("last_received",0)>0?View.VISIBLE:View.GONE);pushReceipt.setText("최근 알림 수신 완료");}
        if(pushToggle!=null){updatingPushControls=true;pushToggle.setChecked(enabled);updatingPushControls=false;}
    }
    private Switch preferenceSwitch(LinearLayout parent,String label,boolean checked) {
        Switch toggle=new Switch(this);toggle.setText(label);toggle.setTextSize(15);toggle.setTextColor(INK);toggle.setChecked(checked);
        toggle.setMinHeight(dp(56));toggle.setPadding(0,dp(8),0,dp(8));parent.addView(toggle,new LinearLayout.LayoutParams(-1,-2));return toggle;
    }
    private void enableNotifications() {
        String account=session.userId(); if(account==null){ logout(); return; }
        if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},70);
        else {PushManager.enable(this,endpoint,account);refreshPushStatus();}
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==70) {
            if(results.length>0 && results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED && session.userId()!=null)
                PushManager.enable(this,endpoint,session.userId());
            refreshPushStatus();
        }
    }

    // ---- Family members (owner) ----

    private void invite(String id){
        singleInput("가족 Google 이메일","초대할 가족의 Google 이메일",254,email -> {
            new AlertDialog.Builder(this).setTitle("가족 권한 선택").setItems(new String[]{"가족","조회 전용"},(dialog,selection)->
                request("POST","/v1/homes/"+id+"/invitations",json("email",email,"role",selection==0 ? "member" : "viewer"),reply -> {
                    String code=reply.optString("invitation_token");
                    new AlertDialog.Builder(this).setTitle("초대 코드가 준비됐어요")
                        .setMessage("지정한 Google 계정만 수락할 수 있어요.\n한 번 사용 · 24시간 동안 유효\n\n복사한 코드는 가족에게 직접 전달해 주세요.")
                        .setPositiveButton("코드 복사",(d,w)-> {
                            ClipboardManager clipboard=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
                            ClipData clip=ClipData.newPlainText("가족 초대 코드",code);
                            android.os.PersistableBundle extras=new android.os.PersistableBundle();
                            extras.putBoolean(android.content.ClipDescription.EXTRA_IS_SENSITIVE,true); clip.getDescription().setExtras(extras);
                            clipboard.setPrimaryClip(clip); message("초대 코드를 복사했어요.");
                        }).setNegativeButton("닫기",null).show();
                })).show();
        });
    }
    private void members(){
        if(currentHome==null){start();return;}
        viewMode="members";routeArg="";generation++;working(false);
        String[] titles=titles();screen(titles[0],titles[1]);
        final String id=currentHome;
        text(page,"가족을 확인하고 있어요…",14,MUTED,false);
        if(currentHouse==null) syncHome();
        request("GET","/v1/homes/"+id+"/members",null,reply -> replacePage(()->renderMembers(id,reply.optJSONArray("members"))));
    }
    private void renderMembers(String id,JSONArray list) {
        if(list==null) return;
        for(int index=0;index<list.length();index++){
            JSONObject person=list.optJSONObject(index); if(person==null) continue;
            LinearLayout item=card(); TextView email=text(item,person.optString("email"),16,INK,true);
            email.setCompoundDrawables(new FamilyIcon("family",ACCENT,dp(20)),null,null,null);email.setCompoundDrawablePadding(dp(10));
            boolean active=person.optInt("active")==1;
            TextView memberRole=text(item,active ? role(person.optString("role")) : "참여 해제됨",13,active?MUTED:DANGER,false);memberRole.setPadding(dp(30),0,0,dp(2));
            if(active && !person.optString("role").equals("owner")) {
                button(item,"권한 변경",false,()-> new AlertDialog.Builder(this).setTitle("가족 권한 변경")
                    .setItems(new String[]{"가족","조회 전용"},(d,selection)->request("PATCH","/v1/homes/"+id+"/members/"+person.optString("id"),
                        json("role",selection==0 ? "member" : "viewer"),r -> members())).show());
                danger(button(item,"가족 참여 해제",false,()-> new AlertDialog.Builder(this).setTitle("가족 참여를 해제할까요?")
                    .setMessage("이 가족은 우리 집의 기록을 볼 수 없게 됩니다.").setNegativeButton("취소",null)
                    .setPositiveButton("참여 해제",(d,w)->request("POST","/v1/homes/"+id+"/members/"+person.optString("id")+"/revoke",json(),r -> members())).show()));
            }
        }
    }
}
