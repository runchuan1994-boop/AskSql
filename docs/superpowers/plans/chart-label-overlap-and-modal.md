# 图表 X 轴标签优化 + 大图弹窗 设计方案

> 状态：计划中
> 范围：纯前端（React + Recharts）
> 目标：解决 X 轴标签重叠/不可读问题，同时提供大图查看能力

---

## 背景与问题

当前图表（折线图/柱状图/面积图）的 X 轴标签在以下场景不可读：

1. **数据点多**（> 10 个）：标签挤在一起，文字重叠
2. **标签文本长**（如完整日期 `2024-06-01T00:00:00`、长分类名）：即使只有几个也可能重叠
3. **容器窄**（移动端/侧边栏场景）：可用宽度不足

之前的 `interval={0}` 方案保证了所有标签都显示，但带来了重叠问题；`interval="preserveEnd"` 又会省略大部分标签。

需要一个**动态自适应**的方案，根据实际可用宽度和标签长度自动选择最佳展示策略。

同时，用户可能需要仔细看图表细节，提供一个**点击放大**的能力。

---

## 方案总览

分两步实施：

| 阶段 | 功能 | 优先级 | 复杂度 |
|------|------|--------|--------|
| Phase 1 | 图表放大弹窗（点击图表 → Modal 大图） | P0 | 低 |
| Phase 2 | X 轴标签自适应密度算法 | P1 | 中 |

全部在前端处理，不需要后端改动。

---

## Phase 1：图表放大弹窗

### 需求

用户点击图表卡片任意位置，弹出一个居中的 Modal，图表以更大尺寸展示，便于查看细节。

### 交互设计

```
┌─────────────────────────────────────┐
│  ✕  每月订单总金额趋势         折线图 │  ← 标题栏 + 关闭按钮
├─────────────────────────────────────┤
│                                     │
│         大尺寸折线图                 │  ← 图表占 Modal 主体 80% 宽度
│         （宽度 ~800px）              │
│                                     │
│                                     │
└─────────────────────────────────────┘
```

1. 图表卡片加上 `cursor: zoom-in` 样式，暗示可点击
2. 点击后弹出 Modal，背景半透明遮罩
3. Modal 内图表重新渲染，使用更大容器（宽度 700-900px，高度 400px）
4. 点击遮罩 / 关闭按钮 / ESC 键 → 关闭
5. 大图和小图使用同一个 `ChartRenderer` 组件，只是容器尺寸不同

### 技术方案

- **组件**：`ChartModal`（新组件）
- **状态管理**：局部 state（`isOpen`, `activeChart`），放在 `ChartGrid` 层
- **复用**：直接复用 `ChartRenderer`，不传额外 props，靠 ResponsiveContainer 自动适应父容器尺寸
- **动画**：淡入淡出

### 组件结构

```
ChartGrid
  ├── ChartCard (× N)
  │     └── 点击 → setActiveChart(chart)
  └── ChartModal (条件渲染)
        ├── ModalHeader (title + 类型标签 + 关闭按钮)
        └── ModalBody
              └── ChartRenderer (同一组件，容器更大)
```

### 待确认问题

- [ ] Modal 里是否需要展示数据表格？（当前设计：只展示图表，表格在下面已有）
- [ ] 是否支持下载图片？（后续迭代，用 recharts-to-image 或 svg → canvas）

---

## Phase 2：X 轴标签自适应密度算法

### 核心思路

**不要硬编码 interval**，而是：

1. **计算**：根据图表可用宽度、标签数量、标签文字平均长度，判断是否会重叠
2. **分级处理**：
   - 不重叠 → 全部显示（`interval={0}`）
   - 轻度重叠 → 标签旋转一定角度
   - 旋转后仍重叠 → 增大 interval（间隔显示标签）
3. **响应式**：窗口 resize 时重新计算

### 算法设计

#### 2.1 输入

```typescript
interface AutoIntervalInput {
  chartWidth: number          // 图表实际宽度（px）
  labelCount: number          // 数据点总数
  labels: string[]            // 所有标签文本
  fontSize: number            // 字体大小（默认 11）
  fontFamily: string          // 字体
  minGap?: number             // 标签间最小间距（默认 8px）
  maxRotation?: number        // 最大旋转角度（默认 -45°）
}
```

#### 2.2 输出

```typescript
interface AutoIntervalResult {
  interval: number | 'preserveStartEnd' | 'preserveStart'
  angle: number               // 旋转角度（0 表示不旋转）
  textAnchor: 'end' | 'middle' // 对齐方式
}
```

#### 2.3 算法步骤

```
函数 computeAutoInterval(input):
  1. 用 Canvas measureText 计算每个标签的宽度
  2. 计算平均标签宽度 avgWidth
  3. 计算理论所需总宽度 = labelCount * avgWidth + (labelCount-1) * minGap
  4. 如果理论宽度 <= chartWidth * 0.9:
       → 返回 { interval: 0, angle: 0, textAnchor: 'middle' }
  5. 否则尝试旋转：
       - 旋转 maxAngle（如 -45°）后，标签水平投影宽度 = avgWidth * cos(|angle|) + fontSize * sin(|angle|)
       - 重新计算理论总宽度
       - 如果 <= chartWidth * 0.9:
         → 返回 { interval: 0, angle: maxAngle, textAnchor: 'end' }
  6. 旋转后仍不够 → 计算最大可显示标签数：
       - maxVisible = floor(chartWidth * 0.9 / (rotatedLabelWidth + minGap))
       - interval = ceil(labelCount / maxVisible)
       - 返回 { interval, angle: maxAngle, textAnchor: 'end' }
  7. 如果 interval 太大（> labelCount / 3）：
       → 改用 'preserveStartEnd'，只保留首尾 + 中间几个
```

#### 2.4 边界情况

| 场景 | 处理 |
|------|------|
| 只有 2-3 个数据点 | 全显示，不旋转 |
| 标签很短（2-3 个字） | 可以放更多，降低 interval |
| 标签很长（>15 字） | 更早进入旋转 + 更大 interval |
| 图表很宽（> 800px） | 可以显示更多标签 |
| 图表很窄（< 300px） | 直接用 `preserveStartEnd` |

### 技术实现

#### 2.4.1 Hook：`useAutoXInterval`

```typescript
function useAutoXInterval(
  chartRef: RefObject<HTMLDivElement>,
  labels: string[],
  options?: AutoIntervalOptions,
): AutoIntervalResult
```

- 用 `ResizeObserver` 监听图表容器宽度变化
- 用 `canvas.measureText` 计算文字宽度（创建一个离屏 canvas）
- 返回 interval / angle / textAnchor

#### 2.4.2 应用到图表组件

在 `LineChartView` / `BarChartView` / `AreaChartView` 中：

```tsx
const chartRef = useRef<HTMLDivElement>(null)
const { interval, angle, textAnchor } = useAutoXInterval(
  chartRef,
  data.map(d => String(d[xField] ?? '')),
  { fontSize: 11, fontFamily: 'inherit' }
)

// ...
<div ref={chartRef} className="w-full h-64">
  <ResponsiveContainer>
    <XAxis
      dataKey={xField}
      interval={interval}
      angle={angle}
      textAnchor={textAnchor}
      height={angle !== 0 ? 60 : 30}
      tickFormatter={formatX}
      ...
    />
  </ResponsiveContainer>
</div>
```

### 性能考虑

- 计算是同步的，但只在 resize 时触发（有 debounce）
- `measureText` 很快，几百个标签也 < 1ms
- 不需要 requestAnimationFrame

### 为什么不用 Recharts 自带的 `interval="auto"`？

Recharts 的 `interval="auto"` 也是自动计算间隔，但：
1. 它不考虑旋转，不会自动加角度
2. 它的计算基于刻度线间距，不是基于实际文字宽度
3. 不可控——不知道它会显示几个标签

自己实现更精细，可以和旋转联动。

---

## 实施清单

### Phase 1 待办

- [ ] 新建 `ChartModal` 组件
  - [ ] Modal 容器（遮罩 + 居中 + 动画）
  - [ ] 标题栏（图表标题 + 类型标签 + 关闭按钮）
  - [ ] 图表主体（响应式高度）
  - [ ] ESC 键关闭、点击遮罩关闭
- [ ] 修改 `ChartGrid`
  - [ ] 每个图表卡片加 `cursor: zoom-in`
  - [ ] 点击打开 Modal
  - [ ] 传递当前 chart + result
- [ ] 玻璃拟态样式匹配
- [ ] 测试：小图、大图数据一致 / 交互正常

### Phase 2 待办

- [ ] 新建 `useAutoXInterval` hook
  - [ ] Canvas 文字宽度测量工具函数
  - [ ] 核心算法（重叠判断 → 旋转 → 间隔）
  - [ ] ResizeObserver 监听
  - [ ] debounce 优化
- [ ] 应用到 `LineChartView`
- [ ] 应用到 `BarChartView`
- [ ] 应用到 `AreaChartView`
- [ ] 测试各种场景
  - [ ] 少数据（3 点）→ 全显示不旋转
  - [ ] 中数据（12 点）→ 旋转
  - [ ] 多数据（30 点）→ 旋转 + 间隔
  - [ ] 超长标签 → 更早旋转 + 更大间隔
  - [ ] 窄容器（300px）→ preserveStartEnd
  - [ ] 宽容器（1000px）→ 显示更多
  - [ ] resize 响应正确

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `src/components/chart/ChartModal.tsx` | 新增 |
| `src/components/chart/ChartGrid.tsx` | 增加点击打开 Modal 逻辑 |
| `src/hooks/useAutoXInterval.ts` | 新增（Phase 2） |
| `src/components/chart/LineChartView.tsx` | 接入 hook |
| `src/components/chart/BarChartView.tsx` | 接入 hook |
| `src/components/chart/AreaChartView.tsx` | 接入 hook |

---

## 后续可扩展（暂不做）

1. **图表下载**：Modal 里加个下载按钮，导出 PNG
2. **Y 轴自适应**：Y 轴数值也可以做智能格式化（大数自动转 K/M/B 单位）
3. **标签省略号**：超长标签加 tooltip 显示完整文本
4. **饼图标签优化**：饼图的 label 也有重叠问题，可以用引导线方案
