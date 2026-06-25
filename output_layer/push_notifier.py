        # ========== 相对强度 ==========
        if hasattr(result, 'relative_strength') and result.relative_strength:
            lines.append("")
            lines.append("【📊 相对强度】")
            # 只展示持仓板块
            for fund_code, fund_info in self.holding_map.items():
                for sec in fund_info.get('sectors', []):
                    if sec in result.relative_strength:
                        rs = result.relative_strength[sec]
                        ratio = rs.get('strength_ratio', 1.0)
                        interp = rs.get('interpretation', '中性')
                        emoji = "🟢" if interp == "强势" else "🟡" if interp == "中性" else "🔴"
                        lines.append(f"    {sec}: {emoji} {ratio:.2f} ({interp})")
                        break
