package com.aircon.a50manager;

import android.app.Activity;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private TextView status;
    @Override public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setTurnScreenOn(true);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int)(24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this);
        title.setText("A50 관리 자동 복구");
        title.setTextSize(26);
        layout.addView(title);
        TextView description = new TextView(this);
        description.setText("재부팅 후 무선 관리 연결을 복구합니다.\n\nWi-Fi 연결을 확인하며, 15분 간격의 보조 점검도 예약합니다. 안드로이드가 작업 시점을 조정할 수 있습니다.\n\n기존 페어링과 Wi-Fi 신뢰 확인을 그대로 사용합니다.");
        description.setTextSize(17);
        description.setPadding(0, padding, 0, padding);
        layout.addView(description);
        status = new TextView(this);
        status.setTextSize(18);
        layout.addView(status);
        Button enable = new Button(this);
        enable.setText("자동 복구 켜기");
        enable.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                Maintenance.setEnabled(MainActivity.this, true);
                Maintenance.restore(MainActivity.this);
                refresh();
            }
        });
        layout.addView(enable);
        Button disable = new Button(this);
        disable.setText("자동 복구 끄기");
        disable.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                Maintenance.setEnabled(MainActivity.this, false);
                refresh();
            }
        });
        layout.addView(disable);
        setContentView(layout);
        Maintenance.schedule(this);
    }
    @Override public void onResume() {
        super.onResume();
        Maintenance.restore(this);
        refresh();
    }
    private void refresh() {
        String enabled = Maintenance.enabled(this) ? "켜짐" : "꺼짐";
        String permission = Maintenance.permissionGranted(this) ? "허용" : "설정 필요";
        int wifiAdb = Settings.Global.getInt(getContentResolver(), "adb_wifi_enabled", 0);
        status.setText("자동 복구: " + enabled + "\n관리 권한: " + permission
            + "\n무선 디버깅: " + (wifiAdb == 1 ? "켜짐" : "꺼짐")
            + "\n집 Wi-Fi 자동 확인: " + (getSharedPreferences("recovery", MODE_PRIVATE)
                .getBoolean("auto_confirm_enabled", false) ? "켜짐" : "꺼짐")
            + "\n\n" + getSharedPreferences("recovery", MODE_PRIVATE).getString("last_result", ""));
    }
}
