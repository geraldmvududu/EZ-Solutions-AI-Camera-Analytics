import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import * as api from "../api";
import type { Camera } from "../types";

const STATUS_COLOR: Record<string, string> = {
  ONLINE: "#14b8a6",
  OFFLINE: "#5a6472",
  ERROR: "#ef4444",
  DISABLED: "#5a6472",
};

export function CameraListScreen({ navigation }: { navigation: any }) {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setCameras(await api.listCameras());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={styles.container}>
      <FlatList
        data={cameras}
        keyExtractor={(c) => c.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#14b8a6" />}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={<Text style={styles.empty}>No cameras configured yet.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => navigation.navigate("CameraDetail", { camera: item })}>
            <View style={styles.row}>
              <Text style={styles.name}>{item.name}</Text>
              <View style={[styles.dot, { backgroundColor: STATUS_COLOR[item.status] }]} />
            </View>
            <Text style={styles.meta}>
              {item.camera_code} · {item.location || "No location set"}
            </Text>
            <Text style={styles.meta}>
              AI: {item.ai_enabled ? "ON" : "OFF"} · REC: {item.recording_enabled ? "ON" : "OFF"}
            </Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e14" },
  card: { backgroundColor: "#151b2b", borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: "#1e2638" },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  name: { color: "#f1f5f9", fontSize: 16, fontWeight: "600" },
  meta: { color: "#94a3b8", fontSize: 12, marginTop: 4 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  empty: { color: "#5a6472", textAlign: "center", marginTop: 40 },
});
