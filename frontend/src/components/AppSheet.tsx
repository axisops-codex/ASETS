import React, { forwardRef, useCallback, useMemo } from "react";
import { View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import BottomSheet, { BottomSheetBackdrop, BottomSheetScrollView } from "@gorhom/bottom-sheet";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useTheme } from "@/src/theme/ThemeProvider";

export type AppSheetRef = BottomSheet;

type Props = {
  children: React.ReactNode;
  snapPoints?: (string | number)[];
  onClose?: () => void;
};

export const AppSheet = forwardRef<BottomSheet, Props>(({ children, snapPoints, onClose }, ref) => {
  const { colors, radius, spacing } = useTheme();
  // A sheet reaches the bottom edge, and Android draws under its
  // navigation bar — without this the last button is untappable.
  const insets = useSafeAreaInsets();
  const points = useMemo(() => snapPoints || ["90%"], [snapPoints]);

  const renderBackdrop = useCallback(
    (props: any) => (
      <BottomSheetBackdrop {...props} appearsOnIndex={0} disappearsOnIndex={-1} opacity={0.5} pressBehavior="close" />
    ),
    []
  );

  return (
    <BottomSheet
      ref={ref}
      index={-1}
      snapPoints={points}
      enablePanDownToClose
      onClose={onClose}
      keyboardBehavior="interactive"
      android_keyboardInputMode="adjustResize"
      backdropComponent={renderBackdrop}
      handleIndicatorStyle={{ backgroundColor: colors.borderStrong, width: 44 }}
      backgroundStyle={{ backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg }}
    >
      <KeyboardAwareScrollView
        ScrollViewComponent={BottomSheetScrollView as any}
        bottomOffset={24}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] + insets.bottom, gap: spacing.md }}
        keyboardShouldPersistTaps="handled"
      >
        {children}
        <View style={{ height: spacing["2xl"] }} />
      </KeyboardAwareScrollView>
    </BottomSheet>
  );
});

AppSheet.displayName = "AppSheet";
