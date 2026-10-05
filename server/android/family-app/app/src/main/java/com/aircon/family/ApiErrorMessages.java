package com.aircon.family;

/** Show an actionable message without displaying server bodies or technical error codes. */
final class ApiErrorMessages {
    static String describe(Exception failure) {
        if (!(failure instanceof ApiClient.Failure))
            return "서버에 연결할 수 없어요. 인터넷 연결과 서버 주소를 확인해 주세요.";
        ApiClient.Failure error=(ApiClient.Failure)failure;
        if (error.status==409) {
            switch(error.code) {
                case "installation_not_registered": return "이 휴대폰의 알림 등록이 완료되지 않았어요. 알림 설정에서 알림을 켜고 연결을 확인해 주세요.";
                case "installation_conflict": return "이 휴대폰의 알림 등록 정보가 다른 등록과 충돌했어요. 집 소유자에게 확인을 요청해 주세요.";
                case "installation_limit": return "이 계정에 등록된 알림 수신 기기가 10대예요. 사용하지 않는 기기에서 알림을 끈 뒤 다시 시도해 주세요.";
                case "already_member": return "이미 이 집에 참여하고 있어요. 집 목록에서 해당 집을 열어 주세요.";
                case "home_hub_exists": return "이 집에는 이미 기기가 등록돼 있어요. 등록된 기기를 확인해 주세요.";
                case "owner_protected": return "집 소유자의 참여나 권한은 여기서 변경할 수 없어요.";
                case "identity_conflict": return "계정 정보가 기존 등록과 일치하지 않아요. 집 소유자에게 확인을 요청해 주세요.";
                default: return "현재 등록 상태에서는 요청을 완료할 수 없어요. 화면을 새로고침한 뒤 다시 확인해 주세요.";
            }
        }
        if (error.status==429) return "요청이 너무 잦아요. 시험 알림은 1분에 한 번 보낼 수 있어요. 잠시 후 다시 시도해 주세요.";
        if (error.status==401) return "로그인을 확인할 수 없어요. 다시 로그인해 주세요.";
        if (error.status==403) {
            if (error.code.equals("owner_required")) return "집 소유자만 사용할 수 있는 기능이에요.";
            if (error.code.equals("account_disabled")) return "이 계정은 현재 사용이 중지돼 있어요. 집 소유자에게 확인해 주세요.";
            return "이 기능을 사용할 권한이 없어요. 집 소유자에게 확인해 주세요.";
        }
        if (error.status==404) {
            if (error.code.equals("invalid_invitation")) return "초대가 만료됐거나 이 계정으로 사용할 수 없어요. 새 초대를 받아 주세요.";
            if (error.code.equals("invalid_claim")) return "기기 등록 코드가 만료됐거나 이미 사용됐어요. 새 코드를 확인해 주세요.";
            return "요청한 항목이 없거나 접근할 수 없어요. 집 목록에서 다시 확인해 주세요.";
        }
        if (error.status==400) {
            if (error.code.equals("confirmation_required")) return "집 이름을 정확히 입력해야 삭제할 수 있어요.";
            if (error.code.equals("invalid_notification_preferences")) return "알림 종류와 온습도 수신 간격을 다시 선택해 주세요.";
            if (error.code.equals("invalid_email")) return "Google 계정 이메일 주소를 확인해 주세요.";
            return "입력 내용을 확인해 주세요.";
        }
        if (error.status==503) {
            if (error.code.equals("notifications_not_configured")) return "서버의 알림 전송 설정이 아직 준비되지 않았어요. 집 소유자에게 확인해 주세요.";
            if (error.code.equals("authentication_not_configured")) return "서버의 로그인 설정이 아직 준비되지 않았어요. 집 소유자에게 확인해 주세요.";
            return "서버가 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.";
        }
        if (error.status>=500) return "서버에서 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.";
        return "서버 응답을 확인할 수 없어요. 서버 주소를 확인한 뒤 다시 시도해 주세요.";
    }
}
