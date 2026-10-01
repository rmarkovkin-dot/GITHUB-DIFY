import sys
import os

# Добавляем корень скилла в пути поиска модулей
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

def main():
    if len(sys.argv) < 2:
        print("ERR|Не указана команда. Доступные: audit, reprice, order, check, usage")
        return

    cmd = sys.argv[1].lower().strip()

    if cmd == 'audit':
        from scripts.run_audit import main as audit_main
        audit_main()

    elif cmd == 'reprice':
        from scripts.repricing import main as reprice_main
        reprice_main()

    elif cmd == 'order':
        # Передаем управление в seller_order с аргументами --cat и --store
        from scripts.seller_order import main as order_main
        order_main()

    elif cmd == 'check':
        from scripts.check_catalog import main as check_main
        check_main()

    elif cmd == 'usage':
        from scripts.audit_usage import main as usage_main
        usage_main()

    else:
        print(f"ERR|Неизвестная команда: {cmd}")

if __name__ == '__main__':
    main()