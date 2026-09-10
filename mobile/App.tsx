import { useEffect } from "react";
import { NavigationContainer, createNavigationContainerRef } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import * as Notifications from "expo-notifications";
import { AuthProvider, useAuth } from "./src/context/AuthContext";
import { LoginScreen } from "./src/screens/LoginScreen";
import { CameraListScreen } from "./src/screens/CameraListScreen";
import { CameraDetailScreen } from "./src/screens/CameraDetailScreen";
import { AlertsScreen } from "./src/screens/AlertsScreen";
import { RecordingsScreen } from "./src/screens/RecordingsScreen";
import { PlaybackScreen } from "./src/screens/PlaybackScreen";
import { NotificationsScreen } from "./src/screens/NotificationsScreen";

const navigationRef = createNavigationContainerRef();

const Stack = createNativeStackNavigator();

const navTheme = {
  dark: true,
  colors: {
    primary: "#14b8a6",
    background: "#0a0e14",
    card: "#0f1420",
    text: "#f1f5f9",
    border: "#1e2638",
    notification: "#ef4444",
  },
} as const;

function LogoutButton() {
  const { logout } = useAuth();
  return (
    <TouchableOpacity onPress={logout} style={{ paddingHorizontal: 12 }}>
      <Text style={{ color: "#14b8a6" }}>Logout</Text>
    </TouchableOpacity>
  );
}

function CamerasHeaderRight({ navigation }: { navigation: any }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <TouchableOpacity onPress={() => navigation.navigate("Notifications")} style={{ paddingHorizontal: 8 }}>
        <Text style={{ color: "#14b8a6" }}>Notifications</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => navigation.navigate("Recordings")} style={{ paddingHorizontal: 8 }}>
        <Text style={{ color: "#14b8a6" }}>Recordings</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => navigation.navigate("Alerts")} style={{ paddingHorizontal: 8 }}>
        <Text style={{ color: "#14b8a6" }}>Alerts</Text>
      </TouchableOpacity>
      <LogoutButton />
    </View>
  );
}

function AppNavigator() {
  const { user, loading } = useAuth();

  // Tapping a delivered push notification (section 39: "Actions: View Camera, View
  // Recording, Acknowledge") opens the Notifications screen, which lists the same
  // real Notification row the backend created when the alert fired.
  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener(() => {
      if (navigationRef.isReady()) {
        navigationRef.navigate("Notifications" as never);
      }
    });
    return () => subscription.remove();
  }, []);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#14b8a6" size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer ref={navigationRef} theme={navTheme as any}>
      <Stack.Navigator>
        {!user ? (
          <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
        ) : (
          <>
            <Stack.Screen
              name="Cameras"
              component={CameraListScreen}
              options={({ navigation }) => ({
                title: "Live Cameras",
                headerRight: () => <CamerasHeaderRight navigation={navigation} />,
              })}
            />
            <Stack.Screen name="CameraDetail" component={CameraDetailScreen} options={{ title: "Camera" }} />
            <Stack.Screen name="Alerts" component={AlertsScreen} options={{ title: "Alerts" }} />
            <Stack.Screen name="Recordings" component={RecordingsScreen} options={{ title: "Recordings" }} />
            <Stack.Screen name="Playback" component={PlaybackScreen} options={{ title: "Playback" }} />
            <Stack.Screen name="Notifications" component={NotificationsScreen} options={{ title: "Notifications" }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <StatusBar style="light" />
      <AppNavigator />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: "#0a0e14", alignItems: "center", justifyContent: "center" },
});
