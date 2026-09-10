import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import * as api from "../api";
import type { NotificationItem } from "../api";

export function NotificationsScreen() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setNotifications(await api.listNotifications());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handlePress(item: NotificationItem) {
    if (!item.is_read) {
      await api.markNotificationRead(item.id);
      load();
    }
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={notifications}
        keyExtractor={(n) => n.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#14b8a6" />}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={<Text style={styles.empty}>No notifications yet.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity style={[styles.card, !item.is_read && styles.unread]} onPress={() => handlePress(item)}>
            <Text style={styles.title}>{item.title}</Text>
            <Text style={styles.body}>{item.body}</Text>
            <Text style={styles.date}>{new Date(item.created_at).toLocaleString()}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e14" },
  card: { backgroundColor: "#151b2b", borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: "#1e2638" },
  unread: { borderColor: "#14b8a6" },
  title: { color: "#f1f5f9", fontSize: 14, fontWeight: "700" },
  body: { color: "#94a3b8", fontSize: 12, marginTop: 4 },
  date: { color: "#5a6472", fontSize: 11, marginTop: 6 },
  empty: { color: "#5a6472", textAlign: "center", marginTop: 40 },
});
