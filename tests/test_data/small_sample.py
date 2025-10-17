#!/usr/bin/env python3
"""
小規模Pythonサンプルファイル
互換性テスト用の基本的なPythonコード
"""

import os
import sys
from typing import List, Dict, Optional

class Calculator:
    """簡単な計算機クラス"""
    
    def __init__(self):
        self.history: List[str] = []
    
    def add(self, a: float, b: float) -> float:
        """加算"""
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def subtract(self, a: float, b: float) -> float:
        """減算"""
        result = a - b
        self.history.append(f"{a} - {b} = {result}")
        return result
    
    def multiply(self, a: float, b: float) -> float:
        """乗算"""
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result
    
    def divide(self, a: float, b: float) -> float:
        """除算"""
        if b == 0:
            raise ValueError("ゼロで割ることはできません")
        result = a / b
        self.history.append(f"{a} / {b} = {result}")
        return result
    
    def get_history(self) -> List[str]:
        """計算履歴を取得"""
        return self.history.copy()
    
    def clear_history(self):
        """計算履歴をクリア"""
        self.history.clear()

def main():
    """メイン関数"""
    calc = Calculator()
    
    # 基本的な計算のテスト
    print("計算機テスト開始")
    
    result1 = calc.add(10, 5)
    print(f"10 + 5 = {result1}")
    
    result2 = calc.subtract(10, 3)
    print(f"10 - 3 = {result2}")
    
    result3 = calc.multiply(4, 7)
    print(f"4 * 7 = {result3}")
    
    result4 = calc.divide(20, 4)
    print(f"20 / 4 = {result4}")
    
    # 履歴の表示
    print("\n計算履歴:")
    for entry in calc.get_history():
        print(f"  {entry}")

if __name__ == "__main__":
    main()