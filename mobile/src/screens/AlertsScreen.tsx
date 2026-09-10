import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import * as api from "../api";
import type { AlertItem } from "../types";

const SEVERITY_COLOR: Record<string, string> = {
  INFO: "#3b82f6",
  LOW: "#22c55e",
  MEDIUM: "#eab308",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};

export function AlertsScreen() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setAlerts(await api.listAlerts());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAcknowledge(id: string) {
    await api.acknowledgeAlert(id);
    load();
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={alerts}
        keyExtractor={(a) => a.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#14b8a6" />}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={<Text style={styles.empty}>No alerts yet.</Text>}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <View style={styles.row}>
              <Text style={styles.type}>{item.alert_type.replace(/_/g, " ")}</Text>
              <View style={[styles.badge, { backgroundColor: SEVERITY_COLOR[item.severity] + "33" }]}>
                <Text style={[styles.badgeText, { color: SEVERITY_COLOR[item.severity] }]}>{item.severity}</Text>
              </View>
            </View>
            <Text style={styles.meta}>{new Date(item.created_at).toLocaleString()}</Text>
            <Text style={styles.meta}>Status: {item.status}</Text>
            {item.status === "NEW" && (
              <TouchableOpacity style={styles.ackButton} onPress={() => handleAcknowledge(item.id)}>
                <Text style={styles.ackButtonText}>Acknowledge</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e14" },
  card: { backgroundColor: "#151b2b", borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: "#1e2638" },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  type: { color: "#f1f5f9", fontSize: 15, fontWeight: "600" },
  meta: { color: "#94a3b8", fontSize: 12, marginTop: 4 },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  ackButton: { marginTop: 10, backgroundColor: "#0d9488", borderRadius: 6, padding: 8, alignItems: "center" },
  ackButtonText: { color: "#fff", fontWeight: "600", fontSize: 12 },
  empty: { color: "#5a6472", textAlign: "center", marginTop: 40 },
});
