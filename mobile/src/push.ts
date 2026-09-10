import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { apiRequest } from "./api/client";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/** Registers this device for push (section 39/40) via Expo's push service — not raw
 * FCM/APNs, so no Firebase project or Apple Developer account is required to receive
 * real notifications through the standard Expo managed workflow. Returns the token it
 * registered, or null if permission was denied or this isn't a physical device (the
 * simulator/emulator without Google Play services can't receive a real push token). */
export async function registerForPushNotifications(): Promise<string | null> {
  if (!Device.isDevice) {
    console.warn("Push notifications require a physical device (or an emulator with Google Play services).");
    return null;
  }

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "default",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#14b8a6",
    });
  }

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== "granted") {
    console.warn("Push notification permission was denied.");
    return null;
  }

  const { data: token } = await Notifications.getExpoPushTokenAsync();

  try {
    await apiRequest("/api/push-tokens", { method: "POST", body: { token, platform: "expo" } });
  } catch (err) {
    console.warn("Failed to register push token with backend:", err);
  }

  return token;
}

export async function unregisterPushToken(token: string): Promise<void> {
  try {
    await apiRequest("/api/push-tokens", { method: "DELETE", body: { token } });
  } catch {
    /* best-effort — logging out shouldn't fail if this doesn't succeed */
  }
}
