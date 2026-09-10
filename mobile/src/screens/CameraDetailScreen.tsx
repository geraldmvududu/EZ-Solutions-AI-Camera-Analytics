import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { WebView } from "react-native-webview";
import { getStreamUrl } from "../api/client";
import type { Camera } from "../types";

/** Live view via WebView (section 38). React Native's <Image> component can't render
 * a multipart/x-mixed-replace MJPEG stream — that's a browser-engine feature. A WebView
 * embeds the platform's real browser engine (Chromium/WebKit), which does support it,
 * so this renders the same real annotated frames the web dashboard shows, not a
 * simulated preview. */
function LiveStream({ cameraId }: { cameraId: string }) {
  const [streamUrl, setStreamUrl] = useState<string | null>(null);

  useEffect(() => {
    getStreamUrl(cameraId).then(setStreamUrl);
  }, [cameraId]);

  if (!streamUrl) {
    return <ActivityIndicator color="#14b8a6" />;
  }

  const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="margin:0;background:#000;"><img src="${streamUrl}" style="width:100%;height:100%;object-fit:contain;" /></body></html>`;

  return <WebView originWhitelist={["*"]} source={{ html }} style={{ flex: 1, backgroundColor: "#000" }} />;
}

export function CameraDetailScreen({ route }: { route: any }) {
  const camera = route.params.camera as Camera;
  const canStream = camera.status === "ONLINE";

  return (
    <View style={styles.container}>
      <View style={styles.videoBox}>
        {canStream ? (
          <LiveStream cameraId={camera.id} />
        ) : (
          <Text style={styles.placeholderText}>Camera is offline — no live stream available</Text>
        )}
      </View>
      <Text style={styles.name}>{camera.name}</Text>
      <Text style={styles.meta}>{camera.camera_code} · {camera.location || "No location set"}</Text>
      <Text style={styles.meta}>Status: {camera.status}</Text>
      <Text style={styles.meta}>Capture FPS: {camera.capture_fps}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e14", padding: 16 },
  videoBox: {
    aspectRatio: 16 / 9,
    backgroundColor: "#000",
    borderRadius: 10,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#1e2638",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  placeholderText: { color: "#5a6472", fontSize: 12, textAlign: "center", padding: 20 },
  name: { color: "#f1f5f9", fontSize: 20, fontWeight: "700" },
  meta: { color: "#94a3b8", marginTop: 6 },
});
