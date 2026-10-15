package com.aircon.family;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.rule.ActivityTestRule;
import org.junit.*;
import org.junit.runner.RunWith;
import static androidx.test.espresso.Espresso.*;
import static androidx.test.espresso.action.ViewActions.*;
import static androidx.test.espresso.assertion.ViewAssertions.matches;
import static androidx.test.espresso.assertion.ViewAssertions.doesNotExist;
import static androidx.test.espresso.matcher.ViewMatchers.*;
import static org.hamcrest.Matchers.*;

@RunWith(AndroidJUnit4.class)
public class FamilyUiTest {
    @Rule public ActivityTestRule<MainActivity> activity=new ActivityTestRule<MainActivity>(MainActivity.class) {
        @Override protected void beforeActivityLaunched() { ServerTrust.forget(androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().getTargetContext()); }
    };
    private void await(String text) throws Exception {
        long deadline=System.currentTimeMillis()+15000;
        while(System.currentTimeMillis()<deadline){
            try {onView(withText(text)).check(matches(isDisplayed())); return;}
            catch(AssertionError|androidx.test.espresso.NoMatchingViewException error){ Thread.sleep(200); }
        }
        onView(withText(text)).check(matches(isDisplayed()));
    }
    private void capture(String name) throws Exception {
        android.graphics.Bitmap image=androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();
        java.io.File root=androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().getTargetContext().getFilesDir();
        try(java.io.FileOutputStream output=new java.io.FileOutputStream(new java.io.File(root,name+".png"))){image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,output);}
        image.recycle();
    }
    /** The app opens the last-used home directly: the 홈 tab is the landing screen, not a home list. */
    @Test public void householdCreationManagementAndLogout() throws Exception {
        await("홈");
        onView(withText("우리 집 시작하기")).check(doesNotExist());
        capture("01-fixture-homes");
        onView(withTagValue(is((Object)"family_home_switcher"))).perform(click());
        await("집 바꾸기");
        onView(withText("새 집 만들기")).perform(click());
        onView(withHint("예: 우리 집")).perform(typeText("New Home"),androidx.test.espresso.action.ViewActions.closeSoftKeyboard());
        onView(withText("확인")).perform(click());
        await("New Home");
        await("아직 연결된 기기가 없어요");
        capture("02-fixture-new-home");
        onView(allOf(withText("알림"),isClickable())).perform(click());
        await("아직 도착한 기록이 없어요");
        onView(allOf(withText("설정"),isClickable())).perform(click());
        onView(withText("가족 관리")).perform(scrollTo(),click());
        await("owner@example.test");
        capture("03-fixture-members");
        onView(withText("홈")).check(doesNotExist());
        onView(withContentDescription("뒤로")).perform(click()); await("가족 관리");
        onView(withText(startsWith("서버 지문 · "))).perform(scrollTo()).check(matches(isDisplayed()));
        onView(withText("서버 지문 · 아직 확인 전")).check(doesNotExist());
        onView(withText("로그아웃")).perform(scrollTo(),click()); await("우리 집을 함께");
        onView(withText("Google로 계속하기")).check(matches(isDisplayed()));
        capture("04-fixture-logout");
        onView(withText("New Home")).check(doesNotExist());
    }
    @Test public void recreationKeepsTheOpenHomeInsteadOfReturningToTheHomeList() throws Exception {
        await("홈");
        onView(allOf(withText("설정"),isClickable())).perform(click());
        await("알림 종류별 중요도");
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().runOnMainSync(()->activity.getActivity().recreate());
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().waitForIdleSync();
        await("알림 종류별 중요도");
        onView(withText("우리 집을 불러오고 있어요…")).check(doesNotExist());
        onView(withText("우리 집 시작하기")).check(doesNotExist());
    }
}
