export interface RuntimeConfig {
  apiBaseUrl: string;
  awsRegion: string;
  userPoolId: string;
  userPoolClientId: string;
  appTitle: string;
  buildId: string;
  dailyNotificationDefaultTime: string;
}

declare global {
  interface Window {
    GOVVUE_CONFIG?: Partial<RuntimeConfig>;
  }
}

const raw = window.GOVVUE_CONFIG ?? {};

export const runtimeConfig: RuntimeConfig = {
  apiBaseUrl: raw.apiBaseUrl ?? '',
  awsRegion: raw.awsRegion ?? 'us-east-1',
  userPoolId: raw.userPoolId ?? '',
  userPoolClientId: raw.userPoolClientId ?? '',
  appTitle: raw.appTitle ?? 'GovVue Light',
  buildId: raw.buildId ?? 'local',
  dailyNotificationDefaultTime: raw.dailyNotificationDefaultTime ?? '06:15',
};
