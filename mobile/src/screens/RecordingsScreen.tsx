import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { apiRequest } from "../api/client";

interface Recording {
  id: string;
  camera_id: string;
  started_at: string;
  duration_seconds: number;
  trigger_type: string;
  is_protected: boolean;
}

export function RecordingsScreen({ navigation }: { navigation: any }) {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setRecordings(await apiRequest<Recording[]>("/api/recordings?limit=100"));
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
        data={recordings}
        keyExtractor={(r) => r.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#14b8a6" />}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={<Text style={styles.empty}>No recordings yet.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => navigation.navigate("Playback", { recording: item })}>
            <View style={styles.row}>
              <Text style={styles.date}>{new Date(item.started_at).toLocaleString()}</Text>
              {item.is_protected && <Text style={styles.locked}>LOCKED</Text>}
            </View>
            <Text style={styles.meta}>
              {item.trigger_type} · {Math.round(item.duration_seconds)}s
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
  date: { color: "#f1f5f9", fontSize: 14, fontWeight: "600" },
  meta: { color: "#94a3b8", fontSize: 12, marginTop: 4 },
  locked: { color: "#ef4444", fontSize: 10, fontWeight: "700" },
  empty: { color: "#5a6472", textAlign: "center", marginTop: 40 },
});
