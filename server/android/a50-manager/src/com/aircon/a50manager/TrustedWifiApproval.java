package com.aircon.a50manager;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.List;

/** Only confirms the wireless debugging dialog for the owner's configured network. */
public final class TrustedWifiApproval extends AccessibilityService {
    private static TrustedWifiApproval connected;
    private boolean scheduled;
    private int checks;
    private long inspectUntil;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable check = new Runnable() {
        @Override public void run() {
            scheduled=false;
            try { confirmKnownNetwork(); }
            catch (RuntimeException failure) { state("INSPECTION_ERROR_"+failure.getClass().getSimpleName()); }
            if (SystemClock.uptimeMillis()<inspectUntil) schedule(500);
        }
    };
    private void schedule(long delay) {
        if (!scheduled) { scheduled=true; handler.postDelayed(check,delay); }
    }
    public static void requestInspection() {
        if (connected != null) {
            connected.inspectUntil=SystemClock.uptimeMillis()+20000;
            connected.schedule(50);
        }
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        // Throttle without cancelling every pending check; a busy System UI must not starve inspection.
        schedule(200);
    }
    public static int inspectionCount() { return connected == null ? 0 : connected.checks; }
    public static boolean isConnected() { return connected != null; }
    @Override public void onServiceConnected() {
        connected=this;
        state("SERVICE_CONNECTED");
        requestInspection();
    }
    @Override public void onInterrupt() { handler.removeCallbacks(check); scheduled=false; }
    @Override public void onDestroy() {
        if (connected==this) connected=null;
        handler.removeCallbacks(check); super.onDestroy();
    }

    private void confirmKnownNetwork() {
        SharedPreferences preferences = getSharedPreferences("recovery", Context.MODE_PRIVATE);
        String network = preferences.getString("approved_network", "");
        String bssid=preferences.getString("approved_bssid", "");
        if (!Maintenance.enabled(this) || !preferences.getBoolean("auto_confirm_enabled", false)
            || network.length() == 0 || bssid.length() == 0) return;
        checks++;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        boolean handled=false;
        if (root != null) {
            try { handled=inspectWindow(root,network,bssid); } finally { root.recycle(); }
        } else state("NO_ACTIVE_WINDOW");
        if (handled) return;
        for (AccessibilityWindowInfo window : getWindows()) {
            AccessibilityNodeInfo other=window.getRoot();
            if (other != null) {
                try { if (inspectWindow(other,network,bssid)) return; }
                finally { other.recycle(); }
            }
        }
    }
    private boolean inspectWindow(AccessibilityNodeInfo root,String network,String bssid) {
        try {
            String owner = String.valueOf(root.getPackageName());
            if (!owner.equals("com.android.systemui") && !owner.equals("com.android.settings") && !owner.equals("android")) {
                state("NON_SYSTEM_WINDOW"); return false;
            }
            String text = allText(root);
            String approvedTitle=getSharedPreferences("recovery",Context.MODE_PRIVATE).getString("approved_dialog_title","");
            boolean exactApprovedTitle=approvedTitle.length()>0 && exactText(root,approvedTitle);
            if (!(text.contains("무선 디버깅") || text.toLowerCase(java.util.Locale.ROOT).contains("wireless debugging") || exactApprovedTitle)) {
                state("NO_WIRELESS_DEBUG_DIALOG"); return false;
            }
            // Exact network text or a quoted/bracketed network in the system dialog.
            if (!(exactText(root, network) || matchesNetwork(text,network))) {
                state("WIRELESS_DIALOG_DIFFERENT_NETWORK"); return true;
            }
            if (!matchesAccessPoint(text,bssid)) { state("WIRELESS_DIALOG_DIFFERENT_ACCESS_POINT"); return true; }
            AccessibilityNodeInfo checkbox = findCheckbox(root);
            if (checkbox == null) { state("NO_CHECKBOX"); return true; }
            if (!checkbox.isChecked()) {
                boolean clicked = checkbox.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                state(clicked ? "CHECKBOX_CHECK_REQUESTED" : "CHECKBOX_CLICK_FAILED");
                if (clicked) schedule(400);
                return true;
            }
            AccessibilityNodeInfo allow = findAllowButton(root);
            if (allow != null && allow.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                state("APPROVED_KNOWN_WIFI");
                getSharedPreferences("recovery",Context.MODE_PRIVATE).edit()
                    .putString("last_approval","APPROVED_KNOWN_WIFI").apply();
                Log.i("A50Recovery", "등록된 집 Wi-Fi의 무선 디버깅 허용창 자동 확인 완료");
            } else state("NO_ALLOW_BUTTON");
            return true;
        } catch (RuntimeException failure) { state("WINDOW_ERROR_"+failure.getClass().getSimpleName()); return false; }
    }
    private void state(String value) {
        SharedPreferences preferences=getSharedPreferences("recovery",Context.MODE_PRIVATE);
        if (!value.equals(preferences.getString("approval_state","")))
            preferences.edit().putString("approval_state",value).apply();
    }
    static boolean matchesNetwork(String text, String network) {
        if (text.contains("\""+network+"\"") || text.contains("“"+network+"”")
            || text.contains("("+network+")")) return true;
        for (String line : text.split("\n")) {
            String trimmed=line.trim();
            if (trimmed.equals(network)) return true;
            String lower=trimmed.toLowerCase(java.util.Locale.ROOT);
            if ((lower.startsWith("network name:") || trimmed.startsWith("네트워크 이름:")
                || trimmed.startsWith("Wi-Fi 네트워크:"))
                && trimmed.substring(trimmed.indexOf(':')+1).trim().equals(network)) return true;
        }
        return false;
    }
    static boolean matchesAccessPoint(String text,String bssid) {
        if (bssid == null || !bssid.matches("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}")) return false;
        return java.util.regex.Pattern.compile("(?i)(?<![0-9a-f:])"+java.util.regex.Pattern.quote(bssid)+"(?![0-9a-f:])").matcher(text).find();
    }
    private static String allText(AccessibilityNodeInfo node) {
        StringBuilder value = new StringBuilder();
        if (node.getText() != null) value.append(node.getText()).append('\n');
        for (int i=0; i<node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { value.append(allText(child)); child.recycle(); }
        }
        return value.toString();
    }
    private static boolean exactText(AccessibilityNodeInfo node, String text) {
        if (node.getText() != null && text.contentEquals(node.getText())) return true;
        for (int i=0; i<node.getChildCount(); i++) {
            AccessibilityNodeInfo child=node.getChild(i);
            if (child != null) {
                boolean found=exactText(child,text); child.recycle();
                if (found) return true;
            }
        }
        return false;
    }
    private static AccessibilityNodeInfo findCheckbox(AccessibilityNodeInfo root) {
        for (String id : new String[]{"com.android.systemui:id/always", "com.android.systemui:id/alwaysAllow", "com.android.settings:id/alwaysAllow"}) {
            List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(id);
            if (!nodes.isEmpty()) return nodes.get(0);
        }
        if (root.isCheckable() && root.isClickable()
            && "android.widget.CheckBox".contentEquals(String.valueOf(root.getClassName()))) {
            String label=String.valueOf(root.getText());
            if (label.contains("계속 허용") || label.contains("항상 허용")
                || label.toLowerCase(java.util.Locale.ROOT).contains("always allow")) return root;
        }
        for (int i=0; i<root.getChildCount(); i++) {
            AccessibilityNodeInfo child=root.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo found=findCheckbox(child);
                if (found != null) return found;
                child.recycle();
            }
        }
        return null;
    }
    private static AccessibilityNodeInfo findAllowButton(AccessibilityNodeInfo root) {
        for (String id : new String[]{"android:id/button1", "com.android.systemui:id/allow_button"}) {
            for (AccessibilityNodeInfo node : root.findAccessibilityNodeInfosByViewId(id)) {
                String text=String.valueOf(node.getText());
                if (node.isClickable() && node.isEnabled()
                    && (text.equals("허용") || text.equals("수락") || text.equalsIgnoreCase("Allow"))) return node;
            }
        }
        return null;
    }
}
