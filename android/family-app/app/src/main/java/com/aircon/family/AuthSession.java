package com.aircon.family;

public interface AuthSession {
    interface TokenResult { void done(String token, Exception error); }
    String userId();
    String email();
    void token(TokenResult result);
    void signIn(Runnable success, java.util.function.Consumer<String> error);
    void signOut();
}
