import java.util.Arrays;
import java.util.HashMap;

public class TwoSum {

    public static int[] twoSum(int[] nums, int target) {

        int[] answer = new int[2];

        HashMap<Integer, Integer> diary = new HashMap<Integer, Integer>();

        diary.put(nums[0], 0);

        for (int i = 1; i < nums.length; i++) {
            if (diary.containsKey(target - nums[i])) {
                answer[0] = diary.get(target - nums[i]);
                answer[1] = i;
            }

            diary.put(nums[i], i);
        }

        return answer;
    }

    public static void main(String[] args) {
        int[] array1 = { 1, 4, 6, 2, 8, 9 };
        System.out.println(Arrays.toString(twoSum(array1, 3)));
    }
}
