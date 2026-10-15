package com.aircon.family;

import android.content.Intent;
import android.content.SharedPreferences;
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

/** Regression coverage for scroll keeping across tabs, refresh and resume, using the signed real APK and existing household. */
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
    private boolean scrollable(ScrollView view) {
        AtomicReference<Boolean> value=new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->value.set(view.canScrollVertically(1)));return value.get();
    }
    private void idle() throws Exception {InstrumentationRegistry.getInstrumentation().waitForIdleSync();Thread.sleep(350);}
    private void ready(String action) throws Exception {
        long deadline=System.currentTimeMillis()+20000;
        while(System.currentTimeMillis()<deadline){android.view.accessibility.AccessibilityNodeInfo n=await(action);if(n.isEnabled()){idle();return;}Thread.sleep(150);}
        fail("A network action did not finish");
    }
    private Switch quietSwitch() {
        AtomicReference<Switch> result=new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(()->{
            java.util.ArrayDeque<android.view.View> views=new java.util.ArrayDeque<>();views.add(activity.getActivity().findViewById(android.R.id.content));
            while(!views.isEmpty()){
                android.view.View v=views.remove();
                if(v instanceof Switch && "정한 시간에는 조용히 받기".contentEquals(((Switch)v).getText()))result.set((Switch)v);
                if(v instanceof android.view.ViewGroup)for(int i=0;i<((android.view.ViewGroup)v).getChildCount();i++)views.add(((android.view.ViewGroup)v).getChildAt(i));
            }
        });assertNotNull(result.get());return result.get();
    }
    @Test public void redesignedNavigationKeepsScrollAndDraft() throws Exception {
        String home=new String(Base64.decode(InstrumentationRegistry.getArguments().getString("home_name_b64",""),Base64.DEFAULT),StandardCharsets.UTF_8);
        openApprovedHome(home);click("알림");await("전체");idle();
        screenshot("18-a50-redesigned-history");
        if(find("보안")!=null) {
            click("보안");idle();
            for(android.view.accessibility.AccessibilityNodeInfo n:nodes(automation.getRootInActiveWindow()))
                assertFalse("Security filter must exclude climate records",n.getText()!=null && n.getText().toString().contains("°"));
            click("전체");
        }
        click("홈");await("집 새로고침");idle();screenshot("17-a50-redesigned-home");
        ScrollView overview=scroll();int homeOffset=0;
        if(scrollable(overview)) {
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->overview.scrollTo(0,200));idle();homeOffset=y(overview);
            assertTrue("Home refresh regression must start below the top",homeOffset>0);
            click("집 새로고침");ready("집 새로고침");assertEquals("Home refresh must keep its offset",homeOffset,y(scroll()));
            click("알림");ready("알림 새로고침");click("홈");idle();assertEquals("Tab return must restore the home offset",homeOffset,y(scroll()));
        }
        click("설정");await("알림 종류별 중요도");idle();screenshot("19-a50-redesigned-settings");
        ScrollView original=scroll();
        SharedPreferences prefs=PushManager.prefs(activity.getActivity());
        boolean stored=PushManager.quietEnabled(prefs);int start=PushManager.quietStart(prefs), end=PushManager.quietEnd(prefs);
        try {
            int offset=(int)(120*activity.getActivity().getResources().getDisplayMetrics().density);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->original.scrollTo(0,offset));idle();int before=y(original);
            assertTrue("The regression must start below the top",before>0);
            screenshot("20-a50-redesigned-notifications");
            try(ParcelFileDescriptor output=automation.executeShellCommand("input keyevent 3")){
                try(java.io.InputStream in=new ParcelFileDescriptor.AutoCloseInputStream(output)){while(in.read()!=-1){}}
            }
            Thread.sleep(250);assertFalse(activity.getActivity().hasWindowFocus());
            activity.getActivity().startActivity(new Intent(activity.getActivity(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT));
            await("알림 종류별 중요도");idle();
            assertSame("Resume must keep the existing screen",original,scroll());
            assertEquals("Resume must keep the scroll position",before,y(original));
            // Choices are saved at once; the redraw keeps the same scroll view and offset.
            Switch quiet=quietSwitch();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->quiet.setChecked(!stored));idle();
            assertEquals(!stored,PushManager.quietEnabled(prefs));
            assertSame(original,scroll());assertEquals("Saving must not jump to the top",before,y(original));
            Switch redrawn=quietSwitch();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(()->redrawn.setChecked(stored));idle();
            assertEquals(stored,PushManager.quietEnabled(prefs));
            // This button is in the current viewport: checking status cannot rebuild the page.
            click("알림 연결 확인");idle();assertSame(original,scroll());assertEquals("Connection check must not jump",before,y(original));
            screenshot("21-a50-scroll-kept-after-save");
            click("홈");await("집 새로고침");click("설정");await("알림 종류별 중요도");idle();
            assertEquals("Returning to settings must restore the route offset",before,y(scroll()));
            Bundle result=new Bundle();result.putString("ui_regression","refresh_tabs_resume_and_saved_choice_keep_scroll_filters_passed");
            result.putInt("scroll_before_px",before);result.putInt("scroll_after_px",y(scroll()));result.putInt("home_refresh_scroll_px",homeOffset);
            InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
        } finally {
            // Only this phone's do-not-disturb choice was touched; restore it exactly. No unregister, no household change.
            PushManager.quietHours(activity.getActivity(),stored,start,end);
        }
    }
}
