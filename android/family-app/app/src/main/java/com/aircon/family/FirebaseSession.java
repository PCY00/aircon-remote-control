package com.aircon.family;

import android.app.Activity;
import android.os.CancellationSignal;
import androidx.credentials.*;
import androidx.credentials.exceptions.*;
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.*;
import java.util.concurrent.Executor;
import java.util.function.Consumer;

final class FirebaseSession implements AuthSession {
    private final Activity activity;
    private final FirebaseAuth auth;
    private final CredentialManager manager;
    private final Executor callbacks;
    FirebaseSession(Activity activity) {
        this.activity=activity; callbacks=activity::runOnUiThread;
        if (FirebaseApp.getApps(activity).isEmpty()) {
            FirebaseApp.initializeApp(activity, new FirebaseOptions.Builder()
                .setApplicationId(BuildConfig.FIREBASE_APP_ID).setApiKey(BuildConfig.FIREBASE_API_KEY)
                .setProjectId(BuildConfig.FIREBASE_PROJECT_ID).build());
        }
        auth=FirebaseAuth.getInstance(); manager=CredentialManager.create(activity);
    }
    public String userId() { return auth.getCurrentUser()==null ? null : auth.getCurrentUser().getUid(); }
    public String email() { return auth.getCurrentUser()==null ? "" : auth.getCurrentUser().getEmail(); }
    public void token(TokenResult result) {
        FirebaseUser user=auth.getCurrentUser();
        if (user==null) { result.done(null,new IllegalStateException("signed out")); return; }
        user.getIdToken(false).addOnCompleteListener(activity, task -> {
            if (task.isSuccessful()) result.done(task.getResult().getToken(),null);
            else result.done(null,new IllegalStateException("token unavailable"));
        });
    }
    public void signIn(Runnable success, Consumer<String> error) {
        GetSignInWithGoogleOption option=new GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID).build();
        GetCredentialRequest request=new GetCredentialRequest.Builder().addCredentialOption(option).build();
        manager.getCredentialAsync(activity,request,new CancellationSignal(),callbacks,
            new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>() {
                public void onResult(GetCredentialResponse response) {
                    try {
                        Credential credential=response.getCredential();
                        if (!(credential instanceof CustomCredential)
                                || !credential.getType().equals(GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL))
                            throw new IllegalArgumentException();
                        String googleToken=GoogleIdTokenCredential.createFrom(credential.getData()).getIdToken();
                        auth.signInWithCredential(GoogleAuthProvider.getCredential(googleToken,null))
                            .addOnCompleteListener(activity, task -> {
                                if (task.isSuccessful()) success.run();
                                else error.accept("Google 로그인에 실패했어요. 연결을 확인하고 다시 시도해 주세요.");
                            });
                    } catch (Exception invalid) { error.accept("로그인 정보를 확인할 수 없어요. 다시 시도해 주세요."); }
                }
                public void onError(GetCredentialException failure) {
                    if (failure instanceof GetCredentialCancellationException) error.accept("로그인을 취소했어요.");
                    else error.accept("Google 계정이 필요해요. 계정과 인터넷 연결을 확인해 주세요.");
                }
            });
    }
    public void signOut() {
        auth.signOut();
        manager.clearCredentialStateAsync(new ClearCredentialStateRequest(),new CancellationSignal(),callbacks,
            new CredentialManagerCallback<Void,ClearCredentialException>() {
                public void onResult(Void unused) {}
                public void onError(ClearCredentialException error) {}
            });
    }
}
