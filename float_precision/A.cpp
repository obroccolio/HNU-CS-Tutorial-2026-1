#include <iostream>
#include <iomanip>
using namespace std;

int main() {
    float balance = 0.0f;
    float prev = -1.0f;
    bool flag=false;
    for (int i = 0; i < 100000000; i++) {
        prev = balance;
        balance += 1.0f;
        // 观察关键区间（接近极限）
        if (balance >= 16777000 && balance <= 16777500&&!flag) {
            cout << fixed << setprecision(0)
                 << "当前: " << balance
                 << "  上一次: " << prev
                 << "  差值: " << balance - prev
                 << endl;
        }
        // 检测“加1失效”
        if (balance == prev&&!flag) {
            cout << "\n加1已经失效！" << endl;
            cout << "停止在: " << fixed << balance << endl;
            flag=true;
        }
        if (flag&&i%10000000==0)
        {
            cout<<"第"<<i<<"次："<<balance<<endl;
        }
    }
    cout << "\n最终余额: " << fixed << balance << endl;
}