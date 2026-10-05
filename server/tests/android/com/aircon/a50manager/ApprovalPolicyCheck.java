package com.aircon.a50manager;

/** Run with the Android API stub jar and compiled helper classes on the JVM. */
public final class ApprovalPolicyCheck {
    private static void check(String body, String network, boolean expected) {
        if (TrustedWifiApproval.matchesNetwork(body, network) != expected) {
            throw new AssertionError("Unexpected approval policy result");
        }
    }
    public static void main(String[] args) {
        check("Network name: HOME-ALLOWED\nAccess point: masked", "HOME-ALLOWED", true);
        check("네트워크 이름: HOME-ALLOWED\n접속 지점: masked", "HOME-ALLOWED", true);
        check("Wi-Fi \"HOME-ALLOWED\"", "HOME-ALLOWED", true);
        check("Wi-Fi\nHOME-ALLOWED\n", "HOME-ALLOWED", true);
        check("Network name: OTHER-HOME\n", "HOME-ALLOWED", false);
        check("Network name: HOME-ALLOWED 2\n", "HOME-ALLOWED", false);
        check("Network name: PREFIX-HOME-ALLOWED\n", "HOME-ALLOWED", false);
        check("Wi-Fi \"HOME-ALLOWED 2\"", "HOME-ALLOWED", false);
        check("HOME-ALLOWED is a word in this unrelated sentence", "HOME-ALLOWED", false);
        if (!TrustedWifiApproval.matchesAccessPoint("BSSID\n02:00:00:00:00:01\n","02:00:00:00:00:01")) throw new AssertionError("Expected AP mismatch");
        if (!TrustedWifiApproval.matchesAccessPoint("BSSID\n02:00:00:00:AA:01\n","02:00:00:00:aa:01")) throw new AssertionError("AP case mismatch");
        if (TrustedWifiApproval.matchesAccessPoint("BSSID\n02:00:00:00:00:02\n","02:00:00:00:00:01")) throw new AssertionError("Other AP approved");
        if (TrustedWifiApproval.matchesAccessPoint("02:00:00:00:00:01:FF","02:00:00:00:00:01")) throw new AssertionError("Partial AP approved");
        if (TrustedWifiApproval.matchesAccessPoint("anything", "")) throw new AssertionError("Unconfigured AP approved");
        System.out.println("APPROVED_WIFI_AND_ACCESS_POINT_POLICY=14_CHECKS_PASS");
    }
}
