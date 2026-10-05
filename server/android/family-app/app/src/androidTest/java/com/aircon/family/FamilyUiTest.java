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
    @Rule public ActivityTestRule<MainActivity> activity=new ActivityTestRule<>(MainActivity.class);
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
    @Test public void householdCreationManagementAndLogout() throws Exception {
        await("시험용 우리 집");
        capture("01-fixture-homes");
        onView(withText("새 집 만들기")).perform(scrollTo(),click());
        onView(withHint("예: 우리 집")).perform(typeText("New Home"),androidx.test.espresso.action.ViewActions.closeSoftKeyboard());
        onView(withText("확인")).perform(click());
        await("New Home");
        await("아직 도착한 기록이 없어요");
        capture("02-fixture-new-home");
        onView(withText("아직 도착한 기록이 없어요")).check(matches(isDisplayed()));
        onView(allOf(withText("설정"),isClickable())).perform(click());
        onView(withText("가족 관리")).perform(scrollTo(),click());
        await("owner@example.test");
        capture("03-fixture-members");
        onView(withText("집으로 돌아가기")).perform(click()); await("New Home");
        onView(allOf(withText("설정"),isClickable())).perform(click());
        onView(withText("로그아웃")).perform(scrollTo(),click()); await("우리 집을 함께");
        onView(withText("Google로 계속하기")).check(matches(isDisplayed()));
        capture("04-fixture-logout");
        onView(withText("New Home")).check(doesNotExist());
    }
}
