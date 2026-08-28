/**
 * X 轴标签自适应密度 Hook
 *
 * 根据图表宽度、标签数量、标签文字长度，动态计算：
 * - interval: 每隔几个数据点显示一个标签
 * - angle: 标签旋转角度
 * - textAnchor: 文字对齐方式
 *
 * 策略（三级降级）：
 *   1. 全显示（不旋转）→ 空间够就用
 *   2. 旋转显示 → 不够就旋转一定角度减小水平投影
 *   3. 旋转 + 间隔显示 → 还是不够就增大 interval
 */
import { useEffect, useRef, useState } from 'react'

export interface AutoXIntervalOptions {
  /** 字体大小（px），默认 11 */
  fontSize?: number
  /** 字体，默认继承 */
  fontFamily?: string
  /** 标签间最小间距（px），默认 8 */
  minGap?: number
  /** 最大旋转角度（绝对值），默认 40 */
  maxRotation?: number
  /** 左右 padding 预留（px），默认 20 */
  paddingX?: number
}

export interface AutoXIntervalResult {
  interval: number | 'preserveStartEnd'
  angle: number
  textAnchor: 'end' | 'middle'
  height: number
}

/**
 * 用 Canvas 测量文本宽度
 */
function measureTextWidth(
  texts: string[],
  fontSize: number,
  fontFamily: string,
): number[] {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) return texts.map(() => fontSize * 4) // 兜底：每个字约 1em 宽
  ctx.font = `${fontSize}px ${fontFamily}`
  return texts.map((t) => ctx.measureText(t).width)
}

/**
 * 计算旋转后标签的水平投影宽度
 * 旋转后，文字本身的宽度投影 = width * cos(|angle|)
 * 另外，旋转中心附近还会有一些高度带来的水平偏移，简化处理：直接加 fontSize
 */
function rotatedWidth(width: number, angleDeg: number, fontSize: number): number {
  const rad = (Math.abs(angleDeg) * Math.PI) / 180
  return width * Math.cos(rad) + fontSize * Math.sin(rad) * 0.5
}

export function useAutoXInterval(
  containerRef: React.RefObject<HTMLDivElement>,
  labels: string[],
  options: AutoXIntervalOptions = {},
): AutoXIntervalResult {
  const fontSize = options.fontSize ?? 11
  const fontFamily = options.fontFamily ?? 'inherit'
  const minGap = options.minGap ?? 8
  const maxRotation = options.maxRotation ?? 40
  const paddingX = options.paddingX ?? 20

  const [result, setResult] = useState<AutoXIntervalResult>({
    interval: 0,
    angle: 0,
    textAnchor: 'middle',
    height: 30,
  })

  const rafRef = useRef<number | null>(null)
  const roRef = useRef<ResizeObserver | null>(null)

  useEffect(() => {
    if (!containerRef.current || labels.length === 0) return

    const container = containerRef.current

    const compute = () => {
      const chartWidth = container.clientWidth - paddingX * 2
      if (chartWidth <= 0) return

      const labelCount = labels.length
      const widths = measureTextWidth(labels, fontSize, fontFamily)
      const maxWidth = Math.max(...widths, 1)

      // ---- 策略 1：全显示，不旋转 ----
      const totalWidth0 =
        maxWidth * labelCount + minGap * (labelCount - 1)
      if (totalWidth0 <= chartWidth && labelCount <= 12) {
        setResult({
          interval: 0,
          angle: 0,
          textAnchor: 'middle',
          height: 30,
        })
        return
      }

      // ---- 策略 2：全显示，旋转 maxRotation 度 ----
      const rotatedMaxWidth = rotatedWidth(maxWidth, maxRotation, fontSize)
      const totalWidthRotated =
        rotatedMaxWidth * labelCount + minGap * (labelCount - 1)
      if (totalWidthRotated <= chartWidth) {
        setResult({
          interval: 0,
          angle: -maxRotation,
          textAnchor: 'end',
          height: 60,
        })
        return
      }

      // ---- 策略 3：旋转 + 间隔显示 ----
      // 计算最多能放多少个标签
      const maxVisible = Math.max(
        2,
        Math.floor((chartWidth + minGap) / (rotatedMaxWidth + minGap)),
      )
      const interval = Math.ceil(labelCount / maxVisible)

      // 如果间隔太大（显示的标签少于 3 个），改用 preserveStartEnd
      const visibleCount = Math.ceil(labelCount / interval)
      if (visibleCount <= 2) {
        setResult({
          interval: 'preserveStartEnd',
          angle: -maxRotation,
          textAnchor: 'end',
          height: 60,
        })
        return
      }

      setResult({
        interval,
        angle: -maxRotation,
        textAnchor: 'end',
        height: 60,
      })
    }

    // 初始计算
    rafRef.current = requestAnimationFrame(compute)

    // 监听 resize
    const ro = new ResizeObserver(() => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(compute)
    })
    ro.observe(container)
    roRef.current = ro

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      ro.disconnect()
    }
  }, [containerRef, labels, fontSize, fontFamily, minGap, maxRotation, paddingX])

  return result
}
