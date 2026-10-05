package com.aircon.family;

import java.net.URI;

/** Only an explicitly chosen HTTPS origin may receive account tokens. */
public final class EndpointPolicy {
    public static String validate(String value, boolean debug) {
        try {
            URI uri = new URI(value.trim());
            if (uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null
                    || uri.getFragment() != null || uri.getPort() == 0 || uri.getPort() > 65535
                    || !(uri.getPath().isEmpty() || uri.getPath().equals("/")))
                throw new IllegalArgumentException();
            boolean local = debug && uri.getScheme().equals("http")
                    && (uri.getHost().equals("127.0.0.1") || uri.getHost().equals("localhost"));
            if (!uri.getScheme().equals("https") && !local) throw new IllegalArgumentException();
            return new URI(uri.getScheme(), null, uri.getHost(), uri.getPort(), null, null, null).toString();
        } catch (Exception error) {
            throw new IllegalArgumentException("연결 주소를 확인해 주세요. HTTPS 주소가 필요합니다.");
        }
    }
    private EndpointPolicy() {}
}
