package com.aircon.family;

import android.app.UiAutomation;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.os.Bundle;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.rule.ActivityTestRule;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import org.junit.Rule;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Signed test APK only: operates the already signed-in release UI, never reads auth tokens. */
@RunWith(AndroidJUnit4.class)
public class OwnFamilySmokeTest {
    @Rule public ActivityTestRule<MainActivity> activity = new ActivityTestRule<>(MainActivity.class);
    protected final UiAutomation automation = InstrumentationRegistry.getInstrumentation()
        .getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);

    protected List<AccessibilityNodeInfo> nodes(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> result = new ArrayList<>();
        if (root == null) return result;
        if ("com.aircon.family".contentEquals(root.getPackageName() == null ? "" : root.getPackageName())) {
            result.add(root);
        }
        for (int i = 0; i < root.getChildCount(); i++) result.addAll(nodes(root.getChild(i)));
        return result;
    }
    protected AccessibilityNodeInfo find(String text) {
        for (AccessibilityNodeInfo node : nodes(automation.getRootInActiveWindow())) {
            if (matches(node,text)) return node;
        }
        return null;
    }
    private boolean matches(AccessibilityNodeInfo node,String text) {
        String value=node.getText()==null?"":node.getText().toString();
        return value.equals(text) || value.startsWith(text+"\n") || text.contentEquals(node.getContentDescription()==null?"":node.getContentDescription());
    }
    protected AccessibilityNodeInfo await(String text) throws Exception {
        long deadline = System.currentTimeMillis() + 20000;
        while (System.currentTimeMillis() < deadline) {
            AccessibilityNodeInfo node = find(text);
            if (node != null) return node;
            Thread.sleep(200);
        }
        throw new AssertionError("Expected own-family UI state did not appear");
    }
    protected void click(String text) throws Exception {
        long deadline = System.currentTimeMillis() + 20000;
        while(System.currentTimeMillis()<deadline){
            for(AccessibilityNodeInfo label:nodes(automation.getRootInActiveWindow())) {
                if(!matches(label,text))continue;
                AccessibilityNodeInfo node=label;
                while(node!=null && !node.isClickable())node=node.getParent();
                if(node==null || !node.isEnabled())continue;
                if(!node.isVisibleToUser()){
                    AccessibilityNodeInfo parent=node.getParent();while(parent!=null&&!parent.isScrollable())parent=parent.getParent();
                    if(parent!=null){
                        Rect target=new Rect(),viewport=new Rect();node.getBoundsInScreen(target);parent.getBoundsInScreen(viewport);
                        int direction=target.bottom<=viewport.top?AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD:AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
                        parent.performAction(direction);
                    }
                    break;
                }
                if(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Own-family enabled action did not accept click: "+text);
    }
    protected void openApprovedHome(String name) throws Exception {
        AccessibilityNodeInfo card=await(name).getParent();AccessibilityNodeInfo open=null;
        for(AccessibilityNodeInfo node:nodes(card))if("집 열기".contentEquals(node.getText()==null?"":node.getText()))open=node;
        assertNotNull("Approved house must have an open action",open);
        long deadline=System.currentTimeMillis()+20000;
        while(!open.isEnabled()&&System.currentTimeMillis()<deadline){Thread.sleep(200);card=await(name).getParent();for(AccessibilityNodeInfo n:nodes(card))if("집 열기".contentEquals(n.getText()==null?"":n.getText()))open=n;}
        assertTrue(open.isEnabled());assertTrue(open.performAction(AccessibilityNodeInfo.ACTION_CLICK));
        await(name);await("소유자 · 우리 가족의 스마트홈");await("우리 집 한눈에");
    }
    protected void openPhoneNotifications() throws Exception {click("설정");await("연결 및 계정");click("알림 설정");await("받고 싶은 알림");}
    protected void screenshot(String name) throws Exception {
        Bitmap original = automation.takeScreenshot();
        assertNotNull("Native capture unavailable", original);
        Bitmap safe = original.copy(Bitmap.Config.ARGB_8888, true);
        original.recycle();
        Canvas canvas = new Canvas(safe);
        Paint background = new Paint(); background.setColor(Color.rgb(225,230,225));
        Paint label = new Paint(); label.setColor(Color.rgb(40,60,50)); label.setTextSize(28);
        for (AccessibilityNodeInfo node : nodes(automation.getRootInActiveWindow())) {
            CharSequence text = node.getText();
            if (text != null && (text.toString().contains("@") || text.toString().startsWith("https://"))) {
                Rect bounds = new Rect(); node.getBoundsInScreen(bounds);
                canvas.drawRect(bounds, background);
                canvas.drawText("[REDACTED]", bounds.left + 8, bounds.top + 38, label);
            }
        }
        File root = InstrumentationRegistry.getInstrumentation().getTargetContext()
            .getExternalFilesDir("test-captures");
        assertNotNull("Own app capture directory unavailable", root);
        if (!root.isDirectory()) assertTrue("Own capture directory creation failed", root.mkdirs());
        Bundle metadata = new Bundle(); metadata.putString("capture_root", root.getAbsolutePath());
        InstrumentationRegistry.getInstrumentation().sendStatus(0, metadata);
        try (FileOutputStream output = new FileOutputStream(new File(root, name + ".png"))) {
            safe.compress(Bitmap.CompressFormat.PNG, 100, output);
        }
        safe.recycle();
    }
    @Test public void existingGoogleSessionCreatesOrReusesNamedHomeAndShowsOwnerPages() throws Exception {
        String encoded = InstrumentationRegistry.getArguments().getString("home_name_b64", "");
        String home = new String(Base64.decode(encoded, Base64.DEFAULT), StandardCharsets.UTF_8);
        assertTrue("Explicit test home name required", home.length() > 0 && home.length() <= 80);
        await("새 집 만들기");
        if (find(home) == null) {
            click("새 집 만들기");
            await("확인");
            AccessibilityNodeInfo input = null;
            for (AccessibilityNodeInfo node : nodes(automation.getRootInActiveWindow())) {
                if ("android.widget.EditText".contentEquals(node.getClassName())) input = node;
            }
            assertNotNull("Own home-name input missing", input);
            Bundle value = new Bundle();
            value.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, home);
            assertTrue("Unicode text input failed", input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, value));
            click("확인");
            Bundle metadata = new Bundle(); metadata.putString("home_action", "created");
            InstrumentationRegistry.getInstrumentation().sendStatus(0, metadata);
        } else {
            AccessibilityNodeInfo card = find(home).getParent();
            AccessibilityNodeInfo open = null;
            for (AccessibilityNodeInfo node : nodes(card)) {
                if ("집 열기".contentEquals(node.getText() == null ? "" : node.getText())) open = node;
            }
            assertNotNull("Existing named home card missing open button", open);
            assertTrue(open.performAction(AccessibilityNodeInfo.ACTION_CLICK));
            Bundle metadata = new Bundle(); metadata.putString("home_action", "reused");
            InstrumentationRegistry.getInstrumentation().sendStatus(0, metadata);
        }
        await(home);
        await("소유자 · 우리 가족의 스마트홈");
        await("아직 도착한 기록이 없어요");
        screenshot("08-a50-real-test-home");
        click("설정");
        click("가족 관리");
        await("가족 관리");
        await("소유자");
        screenshot("09-a50-real-owner-members-redacted");
        click("집으로 돌아가기");
        await(home);
        await("소유자 · 우리 가족의 스마트홈");
    }
}
