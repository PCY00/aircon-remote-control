package com.aircon.family;

import android.content.Intent;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.util.Base64;
import android.widget.ScrollView;
import android.widget.Switch;
import androidx.test.platform.app.InstrumentationRegistry;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;
import static org.junit.Assert.*;

/** Regression coverage for the reported jump, using the signed real APK and existing household. */
public class OwnUiSmokeTest extends OwnFamilySmokeTest {
    private ScrollView scroll() {
        AtomicReference<ScrollView> result=new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->result.set(activity.getActivity().findViewById(android.R.id.content).findViewWithTag("family_scroll")));
        assertNotNull(result.get());return result.get();
    }
    private int y(ScrollView view) {
        AtomicInteger value=new AtomicInteger();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->value.set(view.getScrollY()));return value.get();
    }
    private void idle() throws Exception {InstrumentationRegistry.getInstrumentation().waitForIdleSync();Thread.sleep(350);}
    private void ready(String action) throws Exception {
        long deadline=System.currentTimeMillis()+20000;
        while(System.currentTimeMillis()<deadline){android.view.accessibility.AccessibilityNodeInfo n=await(action);if(n.isEnabled()){idle();return;}Thread.sleep(150);}
        fail("A network action did not finish");
    }
    private Switch climateSwitch() {
        AtomicReference<Switch> result=new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{
            java.util.ArrayDeque<android.view.View> views=new java.util.ArrayDeque<>();views.add(activity.getActivity().findViewById(android.R.id.content));
            while(!views.isEmpty()){
                android.view.View v=views.remove();
                if(v instanceof Switch && "온습도 측정".contentEquals(((Switch)v).getText()))result.set((Switch)v);
                if(v instanceof android.view.ViewGroup)for(int i=0;i<((android.view.ViewGroup)v).getChildCount();i++)views.add(((android.view.ViewGroup)v).getChildAt(i));
            }
        });assertNotNull(result.get());return result.get();
    }
    @Test public void redesignedNavigationKeepsScrollAndDraft() throws Exception {
        String home=new String(Base64.decode(InstrumentationRegistry.getArguments().getString("home_name_b64",""),Base64.DEFAULT),StandardCharsets.UTF_8);
        await("새 집 만들기");openApprovedHome(home);click("기록");await("집에서 일어난 일");idle();
        screenshot("18-a50-redesigned-history");
        click("문");idle();
        for(android.view.accessibility.AccessibilityNodeInfo n:nodes(automation.getRootInActiveWindow()))
            assertFalse("Door filter must exclude climate records",n.getText()!=null && n.getText().toString().startsWith("온습도 측정 ·"));
        click("전체");
        click("홈");await("우리 집 한눈에");idle();screenshot("17-a50-redesigned-home");
        ScrollView overview=scroll();InstrumentationRegistry.getInstrumentation().runOnMainSync(()->overview.scrollTo(0,200));idle();int homeOffset=y(overview);
        assertTrue("Home refresh regression must start below the top",homeOffset>0);
        click("집 새로고침");ready("집 새로고침");assertEquals("Home refresh must keep its offset",homeOffset,y(scroll()));
        click("기록");ready("집 새로고침");click("홈");idle();assertEquals("Tab return must restore the home offset",homeOffset,y(scroll()));
        click("설정");await("집 관리");idle();screenshot("19-a50-redesigned-settings");
        click("알림 설정");await("받고 싶은 알림");idle();screenshot("20-a50-redesigned-notifications");
        ScrollView original=scroll();Switch climate=climateSwitch();
        boolean stored=PushManager.prefs(activity.getActivity()).getBoolean("climate",false);
        try {
            // Leave a draft unsaved to reproduce returning from Android settings/Home.
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->climate.setChecked(!stored));
            int offset=(int)(120*activity.getActivity().getResources().getDisplayMetrics().density);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->original.scrollTo(0,offset));idle();int before=y(original);
            assertTrue("The regression must start below the top",before>0);
            try(ParcelFileDescriptor output=automation.executeShellCommand("input keyevent 3")){
                try(java.io.InputStream in=new ParcelFileDescriptor.AutoCloseInputStream(output)){while(in.read()!=-1){}}
            }
            Thread.sleep(250);assertFalse(activity.getActivity().hasWindowFocus());
            activity.getActivity().startActivity(new Intent(activity.getActivity(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT));
            await("받고 싶은 알림");idle();
            assertSame("Resume must keep the existing screen",original,scroll());
            assertEquals("Resume must keep the scroll position",before,y(original));
            assertEquals("Unsaved choice must survive resume",!stored,climateSwitch().isChecked());
            assertEquals("Draft must not change stored settings",stored,PushManager.prefs(activity.getActivity()).getBoolean("climate",false));
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->climate.setChecked(stored));
            click("선택 저장");idle();assertSame(original,scroll());assertEquals("Save must not jump to the top",before,y(original));
            // This button is in the current viewport: checking status cannot rebuild the page.
            click("알림 연결 확인");idle();assertSame(original,scroll());assertEquals("Connection check must not jump",before,y(original));
            screenshot("21-a50-scroll-kept-after-save");
            click("뒤로");await("집 관리");click("알림 설정");await("받고 싶은 알림");idle();
            assertEquals("Returning to notification settings must restore the route offset",before,y(scroll()));
            Bundle result=new Bundle();result.putString("ui_regression","save_check_resume_and_back_keep_scroll_unsaved_draft_preserved_filters_passed");
            result.putInt("scroll_before_px",before);result.putInt("scroll_after_px",y(scroll()));result.putInt("home_refresh_scroll_px",homeOffset);
            InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
            click("설정");await("집 관리");
        } finally {
            // No unregister and no household deletion. A draft never changes another phone.
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->climate.setChecked(stored));
        }
    }
}
