import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { ResizeMode, Video } from "expo-av";
import { API_URL, tokenStore } from "../api/client";

export function PlaybackScreen({ route }: { route: any }) {
  const recording = route.params.recording as { id: string; started_at: string };
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    tokenStore.getAccess().then((token) => setHeaders(token ? { Authorization: `Bearer ${token}` } : {}));
  }, []);

  if (!headers) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#14b8a6" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Video
        source={{ uri: `${API_URL}/api/recordings/${recording.id}/download`, headers }}
        useNativeControls
        resizeMode={ResizeMode.CONTAIN}
        style={styles.video}
        onError={(e) => console.warn("Playback error", e)}
      />
      <Text style={styles.meta}>Recorded {new Date(recording.started_at).toLocaleString()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e14", padding: 16 },
  center: { flex: 1, backgroundColor: "#0a0e14", alignItems: "center", justifyContent: "center" },
  video: { width: "100%", aspectRatio: 16 / 9, backgroundColor: "#000", borderRadius: 10 },
  meta: { color: "#94a3b8", marginTop: 12, textAlign: "center" },
});
