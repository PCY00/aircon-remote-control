package com.aircon.a50manager;

import android.app.job.JobParameters;
import android.app.job.JobService;

public final class RecoveryJob extends JobService {
    @Override public boolean onStartJob(JobParameters parameters) {
        Maintenance.restore(this);
        return false;
    }
    @Override public boolean onStopJob(JobParameters parameters) {
        return true;
    }
}
