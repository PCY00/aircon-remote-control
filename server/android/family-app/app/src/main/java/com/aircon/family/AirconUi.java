package com.aircon.family;

/** A transmitter acknowledgement does not establish the appliance's measured power state. */
final class AirconUi {
    static final String[] MODES={"냉방","자동","제습","송풍"};
    static final String[] MODE_ACTIONS={"","mode_auto","mode_dry","mode_fan_only"};
    static final String[] FANS={"자동","약풍","중풍","강풍"};
    static final String[] FAN_VALUES={"auto","low","medium","high"};
    static final class Draft {
        int temperature=24, mode=0, fan=0;
        String action() { return mode==0 ? coolingAction(temperature,fan) : MODE_ACTIONS[mode]; }
        int[] save() { return new int[]{temperature,mode,fan}; }
        /** Restores an unsent draft after recreation; values outside the supported range fall back to the defaults. */
        static Draft restore(int[] values,int offset) {
            Draft draft=new Draft();
            if(values==null || offset<0 || values.length<offset+3) return draft;
            if(values[offset]>=17 && values[offset]<=30) draft.temperature=values[offset];
            if(values[offset+1]>=0 && values[offset+1]<MODES.length) draft.mode=values[offset+1];
            if(values[offset+2]>=0 && values[offset+2]<FANS.length) draft.fan=values[offset+2];
            return draft;
        }
    }
    static String coolingAction(int temperature,int fan) {
        if(temperature<17 || temperature>30 || fan<0 || fan>=FAN_VALUES.length)throw new IllegalArgumentException("Unsupported cooling setting");
        return "cool_"+temperature+"_"+FAN_VALUES[fan];
    }
    static String actionLabel(String action) {
        if(action.equals("cool_on"))return "냉방 24°C · 바람 자동";
        if(action.startsWith("cool_")) {
            String[] pieces=action.split("_");
            if(pieces.length==3)for(int i=0;i<FAN_VALUES.length;i++)if(pieces[2].equals(FAN_VALUES[i]))
                return "냉방 "+pieces[1]+"°C · "+FANS[i];
        }
        switch(action) {
            case "power_off": return "전원 끄기";
            case "mode_auto": return "자동 운전";
            case "mode_dry": return "제습 운전";
            case "mode_fan_only": return "송풍 운전";
            case "economy": return "절전";
            case "turbo": return "터보";
            case "led_toggle": return "표시등 바꾸기";
            case "airflow_fix": return "풍향 고정";
            case "swing_toggle": return "스윙 동작 바꾸기";
            default: return "에어컨 명령";
        }
    }
    /** Compact action for the one-line status and tiles: "냉방 24°", "끄기", "제습". */
    static String shortLabel(String action) {
        if(action.equals("cool_on"))return "냉방 24°";
        if(action.startsWith("cool_")) {
            String[] pieces=action.split("_");
            if(pieces.length==3)return "냉방 "+pieces[1]+"°";
        }
        switch(action) {
            case "power_off": return "끄기";
            case "mode_auto": return "자동";
            case "mode_dry": return "제습";
            case "mode_fan_only": return "송풍";
            default: return actionLabel(action);
        }
    }
    /** One word for the command state in the status line. */
    static String stateLabel(String state) {
        switch(state) {
            case "queued": case "dispatched": return "전달 중";
            case "sent": return "전달됨";
            case "failed": return "실패";
            case "expired": return "만료";
            case "cancelled": return "취소됨";
            case "unknown": return "결과 모름";
            default: return "";
        }
    }
    /** States that did not reach the aircon (or may not have); the screen then shows why under the status line. */
    static boolean problem(String state) {
        return state.equals("failed") || state.equals("unknown") || state.equals("expired") || state.equals("cancelled");
    }
    static String confirmation(String action) {
        String result=actionLabel(action)+" 신호를 보내요.";
        if(action.equals("swing_toggle") || action.equals("led_toggle"))
            result+="\n현재 상태를 읽지 못해요. 누를 때마다 동작이 바뀌므로 에어컨 반응을 확인해 주세요.";
        if(action.equals("economy"))
            result+="\n지금 냉방 온도는 그대로 두고 바람만 자동으로 바뀌어요. 냉방 중에만 작동하고, 다른 모드에서는 실패로 표시돼요.";
        return result;
    }
    static boolean pending(String state) { return state.equals("queued") || state.equals("dispatched"); }
    static boolean canSend(boolean allowed, boolean online, String state) {
        return allowed && online && !pending(state);
    }
    static String description(String state,String action) {
        if(state.equals("failed") && action.equals("economy")) return "절전을 보내지 못했어요. 절전은 냉방 중에만 작동해요. 운전 모드와 Pi 연결을 확인해 주세요.";
        return description(state);
    }
    static String description(String state) {
        switch(state) {
            case "queued": return "Pi에 명령을 전달하고 있어요…";
            case "dispatched": return "IR 송신 결과를 기다리고 있어요…";
            case "sent": return "IR 신호를 보냈어요. 실제 작동은 에어컨에서 확인해 주세요.";
            case "failed": return "명령을 보내지 못했어요. Pi와 IR 장치 연결을 확인해 주세요.";
            case "expired": return "시간이 지나 실행하지 않았어요. 연결 상태를 확인해 주세요.";
            case "cancelled": return "권한이나 기기 연결이 바뀌어 실행하지 않았어요.";
            case "unknown": return "실행 결과를 받지 못했어요. 다시 누르기 전에 에어컨을 확인해 주세요.";
            default: return "아직 앱에서 보낸 명령이 없어요.";
        }
    }
}
