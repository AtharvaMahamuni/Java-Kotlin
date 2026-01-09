import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class TargetTriplet {

    public static boolean targetTripletMethod(int[] a, int sum) {
        for (int i = 0; i < a.length - 2; i++) {

            int left = i + 1;
            int right = a.length - 1;

            while (right > left) {
                if (a[i] + a[left] + a[right] == sum)
                    return true;

                else if (a[i] + a[left] + a[right] < sum)
                    left++;

                else
                    right--;
            }
        }

        return false;
    }

    public static List<int[]> targetTripletAdvance(int[] a, int sum) {
        List<int[]> answer = new ArrayList<int[]>();

        for (int i = 0; i < a.length - 2; i++) {
            int left = i + 1;
            int right = a.length - 1;

            while (right > left) {
                if (a[i] + a[left] + a[right] == sum) {
                    answer.add(new int[] { a[i], a[left], a[right] });
                    left++;
                    right--;

                } else if (a[i] + a[left] + a[right] < sum)
                    left++;

                else
                    right--;
            }
        }

        return answer;
    }

    public static void main(String[] args) {

        int[] array1 = { 4, 8, 9, 10, 15, 20, 27, 33 };

        System.out.println(targetTripletMethod(array1, 42));
        System.out.println(targetTripletMethod(array1, 45));

        System.out.println(Arrays.deepToString(targetTripletAdvance(array1, 42).toArray()));
        System.out.println(Arrays.deepToString(targetTripletAdvance(array1, 27).toArray()));
    }
}