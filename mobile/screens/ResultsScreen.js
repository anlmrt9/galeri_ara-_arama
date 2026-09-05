import React from "react";
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Linking } from "react-native";
import { colors } from "../theme";
import { useAppState } from "../AppContext";
import { formatTry, SITE_EMOJI } from "../format";

const SITE_BADGE_COLOR = {
  Otoplus: "#ff4b4b",
  VavaCars: "#1e90ff",
};

export default function ResultsScreen() {
  const { listings, apiBase } = useAppState();

  if (!apiBase) {
    return (
      <View style={styles.centerWrap}>
        <Text style={styles.emptyBody}>Önce Ayarlar sekmesinden API adresini girin.</Text>
      </View>
    );
  }

  const sorted = [...listings].sort((a, b) => new Date(b.scraped_at || 0) - new Date(a.scraped_at || 0));

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.header}>📊 Bulunan Araçlar</Text>
        <Text style={styles.count}>{listings.length} ilan</Text>
      </View>
      <FlatList
        data={sorted}
        keyExtractor={(item, idx) => String(item.id ?? idx)}
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        ListEmptyComponent={
          <Text style={styles.emptyBody}>Henüz sistemde eşleşen bir araç bulunamadı.</Text>
        }
        renderItem={({ item }) => {
          const isNew = item.is_new_listing === 1 || item.is_new_listing === true;
          const badgeColor = SITE_BADGE_COLOR[item.source_site] || colors.violet;
          return (
            <View style={[styles.card, isNew && styles.cardNew]}>
              <View style={styles.cardTop}>
                <View style={[styles.badge, { backgroundColor: badgeColor }]}>
                  <Text style={styles.badgeText}>
                    {SITE_EMOJI[item.source_site] || "🚘"} {item.source_site}
                  </Text>
                </View>
                <Text style={styles.price}>₺{formatTry(item.price)}</Text>
              </View>
              <Text style={styles.title}>
                {item.brand} {item.model} {item.package_trim || ""}
              </Text>
              <Text style={styles.subtitle}>
                {item.year} · {item.km ? Number(item.km).toLocaleString("tr-TR") : "-"} km
              </Text>
              <Text style={styles.meta}>
                Boya: {item.painted_parts || "-"} · Değişen: {item.changed_parts || "-"} · Tramer: ₺
                {formatTry(item.tramer_fee)}
              </Text>
              {!!item.link && (
                <TouchableOpacity onPress={() => Linking.openURL(item.link)}>
                  <Text style={styles.link}>İlana Git ↗</Text>
                </TouchableOpacity>
              )}
            </View>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.navy },
  centerWrap: { flex: 1, backgroundColor: colors.navy, alignItems: "center", justifyContent: "center", padding: 32 },
  emptyBody: { color: colors.muted, fontSize: 14, textAlign: "center", padding: 20 },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 16,
  },
  header: { color: colors.white, fontSize: 18, fontWeight: "600" },
  count: { color: colors.muted, fontSize: 13 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardNew: { borderColor: colors.pink },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  badge: { paddingVertical: 3, paddingHorizontal: 8, borderRadius: 6 },
  badgeText: { color: colors.white, fontSize: 11, fontWeight: "700" },
  price: { color: colors.green, fontSize: 16, fontWeight: "700" },
  title: { color: colors.white, fontSize: 15, fontWeight: "600", marginBottom: 4 },
  subtitle: { color: "#c7cae3", fontSize: 13, marginBottom: 4 },
  meta: { color: colors.muted, fontSize: 12, marginBottom: 8 },
  link: { color: colors.pink, fontSize: 12.5, fontWeight: "600" },
});
